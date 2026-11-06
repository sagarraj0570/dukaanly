# Dukaanly — Transactional Inventory Reservation & Payment-Aware Checkout (Stage 8)

## 1. Overview & Architecture Summary

Dukaanly employs a high-throughput, transactional inventory reservation system designed to eliminate overselling, prevent permanently locked stock, handle abandoned or failed checkouts safely, and guarantee exactly-once inventory restoration.

### Core Architectural Principle
**PostgreSQL is the single authoritative source of truth for inventory, stock availability, reservations, orders, and payment states.**
Redis is utilized solely for caching, PubSub distribution, and distributed rate limiting. Stock reservations and restoration never depend on Redis key lifecycles or process-local in-memory state.

---

## 2. Inventory Availability Invariant

In Dukaanly, available sellable stock is tracked directly in the PostgreSQL `inventory` table:
$$\text{Available Stock} = \text{Inventory.stock}$$

- When an order checkout initiates, the requested quantities are decremented from `Inventory.stock` atomically using optimistic concurrency control (`version = version + 1`) within a row-locked transaction.
- Simultaneously, durable `InventoryReservation` records are inserted with status `active` and an expiration timestamp `expires_at = now() + INVENTORY_RESERVATION_TTL_SECONDS` (default: 900 seconds / 15 minutes).
- **Double deduction is prevented**: Because `Inventory.stock` already reflects sellable stock after active reservations, available stock queries read `Inventory.stock` directly without subtracting active reservations a second time.
- If a reservation transitions to `consumed` (upon confirmed payment), the stock deduction remains permanent.
- If a reservation transitions to `released` (cancellation/payment failure) or `expired` (TTL elapsed), `Inventory.stock` is incremented by the reserved quantity and `Inventory.version` is advanced.

---

## 3. Reservation State Machine

```
               [ Checkout (Stock Decremented) ]
                              │
                              ▼
                        ┌───────────┐
       ┌─────────────── │  ACTIVE   │ ───────────────┐
       │                └───────────┘                │
       │                      │                      │
       ▼                      ▼                      ▼
┌──────────────┐       ┌─────────────┐       ┌──────────────┐
│   CONSUMED   │       │  RELEASED   │       │   EXPIRED    │
│ (Paid/Capt.) │       │ (Cancelled) │       │ (TTL Passed) │
└──────────────┘       └─────────────┘       └──────────────┘
 [Permanent]           [Stock Restored]      [Stock Restored]
```

### Transition Invariants
1. `ACTIVE` $\rightarrow$ `CONSUMED`: Payment verified/captured; stock is permanently claimed; stock is NOT restored.
2. `ACTIVE` $\rightarrow$ `RELEASED`: Order cancelled or payment failed; stock restored exactly once.
3. `ACTIVE` $\rightarrow$ `EXPIRED`: Celery recovery discovers expired reservation; stock restored exactly once.
4. `RELEASED` $\rightarrow$ `*` or `EXPIRED` $\rightarrow$ `*`: Terminal states; cannot be re-activated.
5. `CONSUMED` $\rightarrow$ `RELEASED`: Permitted exclusively during post-confirmation order cancellation (e.g. shop unaccepted order timeout), triggering exactly-once stock restoration via the centralized reservation service.

---

## 4. Exactly-Once Restoration Guarantee & Stage 6 Interaction

All reservation releases and inventory restorations flow strictly through the centralized service:
[`release_order_reservations`](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/backend/app/services/reservation.py)

### Implementation Mechanics:
1. Active (or consumed) reservations for an order are queried with row-level locks (`SELECT ... FOR UPDATE`).
2. An atomic conditional database update is executed:
   ```sql
   UPDATE inventory_reservations
   SET status = :to_status, released_at = :now, release_reason = :reason, version = version + 1
   WHERE id = :res_id AND status IN (:allowed_from_statuses)
   ```
3. Stock restoration is executed **only if `rowcount == 1`**. If concurrent tasks or duplicate webhooks run simultaneously, only the winning transaction receives `rowcount == 1`.
4. Inventory stock increments are sorted deterministically by `product_id` ascending before updating `inventory` rows, preventing deadlock across concurrent multi-item cancellations.

### Prevention of Dual-Path Recovery Collisions (Stage 6 & Stage 8)

Dukaanly Stage 6 provided order recovery jobs (`reconcile_stale_pending_orders`, `reconcile_stale_unaccepted_orders`) that previously cancelled orders and restored stock directly. To prevent collisions where two recovery tasks attempt to restore stock for the same order:

1. **Delegation by Stage 6 Pending Recovery**:
   When `reconcile_stale_pending_orders` encounters an order with `InventoryReservation` records, it delegates execution directly to `_reconcile_single_order_reservation_async`. It enforces the authoritative 4-way payment gateway decision matrix and releases reservations via `release_order_reservations`.
2. **Centralized Release for Confirmed Orders**:
   When `reconcile_stale_unaccepted_orders` cancels a confirmed order via `transition_order`, the state machine checks if the order is reservation-backed. If so, it delegates stock restoration to `release_order_reservations(..., from_statuses=[active, consumed])`.
3. **Strict Prohibition of Independent SQL Increments**:
   The fallback raw `update(Inventory)` in `transition_order` is executed **only** if `total_order_reservations == 0` (for legacy/fixture orders). For reservation-backed orders, independent inventory updates are strictly disabled.
4. **Idempotent Concurrency**:
   Because status transitions require `WHERE status IN (:allowed_from)` and check `rowcount == 1`, racing workers executing Stage 6 or Stage 8 tasks simultaneously will never duplicate stock increments.

---

## 5. Payment-Aware Checkout Workflow

1. **Deterministic Lock Ordering**: Cart items are sorted by `product_id` ascending to ensure lock acquisition order is consistent across all concurrent checkouts.
2. **Optimistic Concurrency Control (OCC)**: `UPDATE inventory SET stock = stock - qty, version = version + 1 WHERE product_id = :id AND version = :exp_ver AND stock >= qty`.
   - If version conflict occurs with sufficient stock, retries once with refreshed state.
   - If stock is genuinely insufficient, rolls back and returns structured `409 Conflict`.
3. **Atomic Multi-Entity Commit**:
   - `Order` created with status `pending`.
   - `OrderItem` snapshots created.
   - `InventoryReservation` created with status `active` and authoritative UTC `expires_at`.
   - `Payment` created with status `created`.
   - `OrderEvent` audit entry recorded.
   - Cart cleared.
   - Transaction committed atomically.

---

## 6. Payment Integration & Security

- **Server-Side Cryptographic Verification**: Razorpay HMAC-SHA256 signatures are calculated and verified server-side only. Client applications never receive secret keys or signing credentials.
- **Sandbox Simulation Support**: In non-production mock mode, `initiate_payment` generates and returns ephemeral `mock_payment_id` and `mock_signature` so the frontend UI can simulate success or failure without hardcoded secrets in the client bundle.
- **Payment Outcomes**:
  - `captured`: Consumes active reservations via `consume_order_reservations`, confirms order.
  - `failed`: Releases active reservations via `release_order_reservations`, restores stock, cancels order.
  - `timeout / unknown`: Retains active state until resolved or expired by the Celery recovery job.

---

## 7. Background Expiration & Reconciliation (Celery Beat)

- **Task Name**: `reconcile_expired_inventory_reservations`
- **Schedule**: Every 60 seconds via Celery Beat.
- **Batch Processing**: Bounded execution (`ORDER_RECOVERY_BATCH_SIZE = 50`) using row-level locking with `FOR UPDATE SKIP LOCKED`.

### Payment Outcome Resolution Policy During Reservation Expiry

When an active reservation's TTL expires (`expires_at <= now()`), the recovery worker executes an authoritative reconciliation check against PostgreSQL records and the upstream payment gateway adapter (`PaymentProvider.fetch_payment_order`).

A pending payment is **not** assumed to be a failed payment. The recovery task enforces a strict 4-way decision matrix:

| Outcome State | Provider / Database Condition | System Action | Inventory Impact |
| :--- | :--- | :--- | :--- |
| **1. Confirmed Success** | Local DB has `PaymentStatus.captured` OR gateway reports status `paid` / `captured`. | `consume_order_reservations(order.id)`; transitions order to `confirmed`. | Stock remains decremented; claimed permanently. |
| **2. Definitive Failure** | All order payments are `failed` / `cancelled` in DB OR gateway reports status `failed` / `cancelled` / `expired`. | Marks payment `failed`; `release_order_reservations(..., to_status=released)`; transitions order to `cancelled`. | Stock restored atomically via OCC integer versioning. |
| **3. Unknown / Ambiguous Outcome** | Gateway lookup raises an error (network timeout, HTTP 5xx, processor unreachable) OR gateway reports in-flight status (`processing`, `authorized`, `in_progress`). | **RETAINS ACTIVE RESERVATION**. Transaction rolls back / skips releasing order; defers to next reconciliation cycle; logs warning `inventory.reconciliation_retained_unknown_outcome`. | Stock is **NOT** released; order remains `pending`. |
| **4. Pending Beyond Defined Policy** | Gateway confirms order was never captured (`created`, `attempted`, `unpaid`) AND reservation TTL has expired; customer abandoned checkout. | Marks payment `cancelled`; `release_order_reservations(..., to_status=expired)`; transitions order to `cancelled`. | Stock restored atomically via OCC integer versioning. |

### Safe Compensating Workflow for Late Payment Success

To prevent race conditions where a customer completes payment at the gateway at the precise moment of reservation expiry and cancellation:

1. **Client Signature Verification (`verify_payment`)**: Rejects verification with `400 Bad Request` if the order was already cancelled.
2. **Provider Webhook (`process_webhook`)**: When a `payment.captured` event arrives for an order that is already in status `cancelled`:
   - The system **NEVER** revives the cancelled order.
   - The system **NEVER** deducts or double-sells inventory stock.
   - The system executes an automated compensating workflow: marks `Payment.status = PaymentStatus.refunded`, records `failure_reason = "late_payment_captured_after_order_cancellation: auto-refunded"`, and invokes `PaymentProvider.refund_payment(...)` to immediately return funds to the customer.
   - A high-severity audit warning `payment.compensating_refund_triggered` is logged.

---

## 8. Client Experience & API Endpoints

- **Countdown & Reservation Summary API**: `GET /api/v1/orders/{order_id}/reservation`
  - Returns overall status (`active`, `consumed`, `released`, `expired`), authoritative `expires_at`, `seconds_remaining`, `server_time`, and item details.
- **Frontend Timer**: Real-time synchronized countdown banner in [`CustomerPayment.tsx`](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/frontend/src/pages/CustomerPayment.tsx) via [`useSynchronizedCountdown`](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/frontend/src/hooks/useSynchronizedCountdown.ts).
- **Graceful Expiration**: When expired, disables payment buttons and displays an alert with an action to return to cart and re-order.

---

## 9. Transaction Lock Ordering Hierarchy & Deadlock Prevention

### Canonical Lock Hierarchy
To prevent database transaction deadlocks (`40P01` / `DeadlockDetectedError`) across concurrent operations competing on the same order, Dukaanly enforces a strict, canonical lock hierarchy across all commerce transactions:

$$\mathbf{Order} \longrightarrow \mathbf{Payment} \longrightarrow \mathbf{InventoryReservation} \longrightarrow \mathbf{Inventory} \ (\text{ordered by } \text{product\_id ASC})$$

### Operation Lock Ordering Mapping

| Operation | 1. Order Lock | 2. Payment Lock | 3. Reservation Lock | 4. Inventory Lock / Update | Deadlock Prevention Guarantee |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Checkout** | Inserts new `Order` row (uncontended) | N/A (uncontended) | Inserts new `InventoryReservation` rows | OCC stock decrement sorted by `product_id ASC` | Deterministic `product_id ASC` order prevents deadlocks between concurrent checkouts sharing products. |
| **2. Payment Verification** | Non-locking `select(Payment.order_id)` $\rightarrow$ `select(Order).with_for_update()` | `select(Payment).with_for_update()` | `consume_order_reservations()` (`with_for_update()` ordered by `product_id ASC`) | Stock remains consumed (no update) | Non-locking `order_id` resolution prevents lock inversion with concurrent cancellation or expiry tasks. |
| **3. Payment Webhook** | Non-locking `select(Payment.order_id)` $\rightarrow$ `select(Order).with_for_update()` | `select(Payment).with_for_update()` | `consume_order_reservations()` or `release_order_reservations()` | If failed/cancelled: restores stock sorted by `product_id ASC` | Locks `Order` before `Payment` before `Reservation`; strictly eliminates deadlocks against customer cancellation. |
| **4. Customer Cancellation** | `select(Order).with_for_update()` | `select(Payment).with_for_update()` (marks uncaptured `cancelled` / captured `refunded`) | `release_order_reservations()` (`with_for_update()` ordered by `product_id ASC`) | Stock incremented sorted by `product_id ASC` | Follows strict canonical sequence; serializes cleanly against concurrent payment webhooks. |
| **5. Shop Rejection** | `select(Order).with_for_update()` | `select(Payment).with_for_update()` (marks uncaptured `cancelled` / captured `refunded`) | `release_order_reservations()` (`with_for_update()` ordered by `product_id ASC`) | Stock incremented sorted by `product_id ASC` | Identical to customer cancellation; follows exact hierarchy. |
| **6. Reservation Expiry** | `select(Order).with_for_update(skip_locked=True)` | `select(Payment).with_for_update()` | `release_order_reservations()` (`with_for_update()` ordered by `product_id ASC`) | Stock incremented sorted by `product_id ASC` | Locks `Order` first, then `Payment`, then releases reservations; concurrent verify/webhook requests serialize cleanly on `Order`. |
| **7. Stage 6 Order Recovery** | `select(Order).with_for_update()` | `select(Payment).with_for_update()` | Delegates to `release_order_reservations()` | Stock incremented sorted by `product_id ASC` | Aligned with Stage 8 centralized reservation service and canonical lock ordering. |

### Elimination of Lock Inversion Defect

**Previous Defect**:
In initial implementations, `verify_payment` and `process_webhook` acquired `Payment` row locks first via `SELECT ... FROM payments WHERE provider_order_id = :id FOR UPDATE`, and subsequently acquired `Order` row locks. Concurrently, recovery tasks and cancellation routines acquired `Order` row locks first and then acquired `Payment` row locks. Under high contention or boundary race conditions, this created a cyclic dependency in PostgreSQL's wait-for graph:
$$\text{Worker A}: \text{Payment} \rightarrow \text{waits for Order}$$
$$\text{Worker B}: \text{Order} \rightarrow \text{waits for Payment} \implies \mathbf{Deadlock \ (40P01)}$$

**Remediation**:
By resolving `order_id` using a non-locking MVCC query (`SELECT order_id FROM payments WHERE provider_order_id = :id`), `verify_payment` and `process_webhook` obtain the parent order identifier without taking any row-level locks. They then acquire the exclusive `Order` lock **first**, followed by the `Payment` lock **second**, bringing all 7 operations into complete alignment.
Verified via concurrent PostgreSQL integration tests:
- `test_concurrency_lock_order_deadlock_prevention`: 0 deadlocks detected under simultaneous payment verification and reservation recovery.
- `test_concurrency_webhook_vs_cancellation_lock_order`: 0 deadlocks detected under simultaneous webhook capture and customer cancellation.

---

## 10. Clock Drift Elimination & Authoritative Stock Release Invariant

### 1. Clock Drift Elimination Architecture
Browser system clocks (`Date.now()`, `new Date()`) are prone to user tampering, timezone misconfigurations, NTP step corrections, and background tab throttling. Comparing server `expires_at` against client `Date.now()` causes severe countdown distortion.

To eliminate clock drift without depending on the client's wall clock:
1. **Server-Side Authoritative Response**:
   `GET /api/v1/orders/{order_id}/reservation` provides both `seconds_remaining` (the exact remaining duration calculated on the backend) and `server_time` (the UTC server generation timestamp).
2. **Monotonic Client Anchoring**:
   The frontend [`useSynchronizedCountdown`](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/frontend/src/hooks/useSynchronizedCountdown.ts) hook anchors `seconds_remaining` to the browser's monotonic clock (`performance.now()`).
   $$\text{elapsedSeconds} = \frac{\text{performance.now()} - \text{anchorPerformanceMs}}{1000}$$
   $$\text{currentRemaining} = \max\left(0, \text{anchorSecondsRemaining} - \text{elapsedSeconds}\right)$$
   Because `performance.now()` measures elapsed time since document creation and advances monotonically:
   - System clock changes have **zero** impact.
   - Background tab throttling or wake-ups automatically reflect the true elapsed time without drift.
   - Each 5-second polling cycle re-anchors the reference smoothly without sudden visual jumps.

### 2. Authoritative Stock Release Invariant
**Strict Invariant: The frontend countdown timer NEVER determines whether inventory stock is released.**
- A local countdown reaching `00:00` is solely a client-side display milestone. It indicates that the estimated payment window has closed, but it does **not** alter backend database state.
- **Backend as Sole Authority**:
  Only PostgreSQL transactions executed by the backend can transition reservations to `expired` or `released` and restore inventory stock.
- **Frontend State Separation**:
  - `isStockReleasedAuthoritatively`: True **only** when `order.status === 'cancelled'` or `reservation.status === 'expired' | 'released'`. Renders the definitive "Reservation Expired — items restored to inventory" notice.
  - `isTimerElapsed` (countdown at 00:00, but stock not yet released): Renders a syncing indicator ("Verifying reservation status with server..."). Payment requests are **not** arbitrarily blocked; if submitted, the backend's atomic transaction decides whether the reservation is still valid or has expired.


