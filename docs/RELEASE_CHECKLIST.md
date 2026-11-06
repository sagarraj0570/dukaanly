# Dukaanly — Release Readiness Checklist

This document defines the mandatory pre-deployment gates, deployment execution steps, and post-deployment operational verification criteria for releasing Dukaanly to production.

---

## 1. Architectural & Scope Compliance Gates

- [x] **Hyperlocal Scope Strictness**: No reviews/ratings, admin dashboards, analytics dashboards, or push/SMS notifications are implemented (`AGENTS.md`).
- [x] **Inventory OCC Enforcement**: Optimistic locking (`version` column) and pessimistic row locking (`SELECT FOR UPDATE`) prevent inventory overselling and race conditions.
- [x] **Geospatial Real Invariants**: All shop discovery, delivery eligibility, and rider dispatch use genuine PostGIS functions (`ST_DWithin`, `ST_Distance`, `location::geography`), never Python planar math.
- [x] **Single Linear Alembic History**: All migrations form an unbroken chain terminating at head revision `2c3278e09b46`.
- [x] **Role-Based Authorization & IDOR Isolation**: Server-side verification on all state-changing endpoints (`user_id == resource.owner_id`).
- [x] **Credential Hygiene**: Zero secrets (JWT keys, DB passwords, Redis credentials, Razorpay secret) exposed to frontend bundles or client logs.

---

## 2. Pre-Deployment Automated Test Verification

| Test Suite | Scope | Target | Result | Status |
| :--- | :--- | :---: | :---: | :---: |
| **Backend Suite** | Unit, API, Concurrency, State Machine | 461 tests | 461 passed, 3 deselected, 0 failed | **PASS** |
| **Stage 10 Suite** | E2E Commerce, IDOR, Concurrency, Token Family | 6 tests | 6 passed, 0 failed | **PASS** |
| **Frontend Suite** | Pages, Components, Three.js, Hooks, State Stores | 118 tests | 118 passed, 0 failed | **PASS** |
| **Frontend Production Build** | TypeScript compilation (`tsc -b`) & Vite build | Bundle generation | Clean build in 1.86s, 0 errors | **PASS** |

---

## 3. Database & Disaster Recovery Verification

- [x] **Pre-Deploy PostGIS Check**: Verified `python -m app.db.init_predeploy` executes `CREATE EXTENSION IF NOT EXISTS postgis;`.
- [x] **Automated Binary Backup**: Tested bit-for-bit `pg_dump -Fc` archive generation (`dukaanly_release_backup.dump`, 221 KB).
- [x] **Full Database Restoration**: Tested `pg_restore --no-owner` into clean database instance (`dukaanly_restore_test`). All 21 tables, spatial geometry columns, and Alembic version verified bit-for-bit.
- [x] **Migration Rollback & Recovery**: Tested `alembic downgrade -1` from `2c3278e09b46` to `d5a8e2b74c10` and re-upgrade to `2c3278e09b46` cleanly without data loss.
- [x] **Connection Budget Validation**: Max application connections capped at 20 (`DB_POOL_SIZE=10`, `DB_MAX_OVERFLOW=10`), leaving 80 connections headroom under PostgreSQL default `max_connections=100`.

---

## 4. Multi-Role End-to-End Workflow Verification

- [x] **Customer Discovery**: PostGIS `ST_DWithin` accurately discovers active, orderable shops in Patna Boring Road within 3,000m radius.
- [x] **Cart & Checkout**: Strict one-shop-per-cart rule enforced (HTTP 409 on cross-shop items); atomic checkout decrements stock and creates `active` inventory reservation.
- [x] **Payment Verification**: Mock Razorpay cryptographic HMAC-SHA256 signature verification confirms order and marks reservation `consumed`.
- [x] **Shop Owner Processing**: Order status transitions cleanly from `confirmed` $\to$ `preparing` $\to$ `ready_for_delivery`.
- [x] **Rider Lifecycle**: Delivery created, assigned to eligible rider, and progressed through `assigned` $\to$ `picked_up` $\to$ `out_for_delivery` $\to$ `delivered`.
- [x] **Customer Visibility**: Real-time delivery status and completed order visible in customer order history.

---

## 5. Security & Authentication Guardrails

- [x] **Token Family Rotation**: Refresh tokens rotate on every refresh with successor tracking (`replaced_by_id`).
- [x] **Token Reuse Detection**: Replaying a rotated refresh token outside the 5.0-second grace window immediately revokes the entire token family.
- [x] **Role-Based Health Diagnostics**: `GET /api/v1/health/diagnostics` returns 401 for unauthenticated requests, 403 for customers, and 200 with operational metrics only for admin users.
- [x] **Rate Limiting Resilience**: Sliding window Redis rate limiter fails open with structured warning logs when Redis is temporarily unreachable, preserving checkout flow.

---

## 6. Deployment Step-by-Step Execution Protocol

1. **Environment Preparation**:
   - Ensure `.env` is populated with strong production secrets (`POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET_KEY`).
   - Confirm `APP_ENV=production` and `DEBUG=false`.
2. **Execute Database Backup**:
   - Run `docker exec dukaanly_postgres pg_dump -U dukaanly_user -d dukaanly -Fc -f /tmp/backup.dump`.
3. **Execute Database Migrations**:
   - Run `docker compose run --rm api alembic upgrade head`.
4. **Deploy Application Containers**:
   - Run `docker compose up -d --build`.
5. **Verify Health Endpoints**:
   - `curl -f http://localhost:8000/api/v1/health/live` $\to$ `{"status": "ok"}`
   - `curl -f http://localhost:8000/api/v1/health/ready` $\to$ `{"status": "ready", ...}`
6. **Post-Deployment Sanity Verification**:
   - Run `python backend/scripts/stage10_benchmark.py` to confirm latency targets:
     - Health Check p95: $< 15$ ms
     - PostGIS Discovery p95: $< 15$ ms
     - Checkout & Reservation p95: $< 50$ ms
     - Payment Verification p95: $< 50$ ms
