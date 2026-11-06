"""
SQL Invariant Verifier for Dukaanly System Test Harness.

Asserts system consistency invariants directly in PostgreSQL/PostGIS,
strictly scoped to the namespaced entities of a given RUN_ID.
Violations fail immediately naming the specific invariant and data.
"""

from typing import List, Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from tests_system.config import ASYNC_DB_URL, SYSTEST_TAG_PREFIX, SYSTEST_SHOP_PREFIX


class InvariantViolationError(AssertionError):
    """Raised when a system consistency invariant is violated."""
    pass


async def verify_system_invariants(run_id: str) -> None:
    """
    Executes all Section G invariant assertions in PostgreSQL scoped to run_id.
    Raises InvariantViolationError if any assertion fails.
    """
    engine = create_async_engine(ASYNC_DB_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    user_pat = f"{SYSTEST_TAG_PREFIX}{run_id}-%"
    shop_pat = f"{SYSTEST_SHOP_PREFIX}{run_id} %"

    async with Session() as session:
        # 1. No Negative Stock
        q1 = await session.execute(
            text("""
                SELECT p.id, p.name, i.stock
                FROM inventory i
                JOIN products p ON i.product_id = p.id
                JOIN shops s ON p.shop_id = s.id
                WHERE s.name LIKE :shop_pat AND i.stock < 0
            """),
            {"shop_pat": shop_pat}
        )
        neg_stock = q1.fetchall()
        if neg_stock:
            raise InvariantViolationError(
                f"INVARIANT VIOLATION: no_negative_stock -> Found negative stock: {neg_stock}"
            )

        # 2. Stock + Reserved Consistency
        q2 = await session.execute(
            text("""
                SELECT p.id, p.name, i.stock, COALESCE(SUM(ir.quantity), 0) AS reserved
                FROM inventory i
                JOIN products p ON i.product_id = p.id
                JOIN shops s ON p.shop_id = s.id
                LEFT JOIN inventory_reservations ir ON ir.product_id = p.id AND ir.status = 'active'
                WHERE s.name LIKE :shop_pat
                GROUP BY p.id, p.name, i.stock
                HAVING i.stock < 0
            """),
            {"shop_pat": shop_pat}
        )
        inconsistent_stock = q2.fetchall()
        if inconsistent_stock:
            raise InvariantViolationError(
                f"INVARIANT VIOLATION: stock_reserved_consistency -> {inconsistent_stock}"
            )

        # 3. No Unavailable Rider Without Active Delivery
        q3 = await session.execute(
            text("""
                SELECT r.id, u.email
                FROM rider_profiles r
                JOIN users u ON r.user_id = u.id
                WHERE u.email LIKE :user_pat
                  AND r.is_available = false
                  AND NOT EXISTS (
                      SELECT 1 FROM deliveries d
                      WHERE d.rider_id = r.id
                        AND d.status IN ('assigned', 'picked_up', 'out_for_delivery')
                  )
            """),
            {"user_pat": user_pat}
        )
        ghost_busy_riders = q3.fetchall()
        if ghost_busy_riders:
            raise InvariantViolationError(
                f"INVARIANT VIOLATION: no_unavailable_rider_without_active_delivery -> Riders marked busy with zero active deliveries: {ghost_busy_riders}"
            )

        # 4. No Rider With Multiple Active Deliveries
        q4 = await session.execute(
            text("""
                SELECT d.rider_id, COUNT(*) as active_count
                FROM deliveries d
                JOIN rider_profiles r ON d.rider_id = r.id
                JOIN users u ON r.user_id = u.id
                WHERE u.email LIKE :user_pat
                  AND d.status IN ('assigned', 'picked_up', 'out_for_delivery')
                GROUP BY d.rider_id
                HAVING COUNT(*) > 1
            """),
            {"user_pat": user_pat}
        )
        multi_delivery_riders = q4.fetchall()
        if multi_delivery_riders:
            raise InvariantViolationError(
                f"INVARIANT VIOLATION: no_rider_with_multiple_active_deliveries -> Rider assigned multiple active deliveries: {multi_delivery_riders}"
            )

        # 5. No Active Delivery Under Terminal Order
        q5 = await session.execute(
            text("""
                SELECT d.id, d.status, o.id, o.status
                FROM deliveries d
                JOIN orders o ON d.order_id = o.id
                JOIN users u ON o.customer_id = u.id
                WHERE u.email LIKE :user_pat
                  AND o.status IN ('delivered', 'cancelled')
                  AND d.status IN ('assigned', 'picked_up', 'out_for_delivery')
            """),
            {"user_pat": user_pat}
        )
        active_on_terminal_order = q5.fetchall()
        if active_on_terminal_order:
            raise InvariantViolationError(
                f"INVARIANT VIOLATION: no_active_delivery_under_terminal_order -> Active delivery under terminal order: {active_on_terminal_order}"
            )

        # 6. No Open Offers On Terminal Deliveries
        q6 = await session.execute(
            text("""
                SELECT doff.id, doff.status, d.id, d.status
                FROM delivery_offers doff
                JOIN deliveries d ON doff.delivery_id = d.id
                JOIN orders o ON d.order_id = o.id
                JOIN users u ON o.customer_id = u.id
                WHERE u.email LIKE :user_pat
                  AND d.status IN ('delivered', 'cancelled')
                  AND doff.status = 'offered'
            """),
            {"user_pat": user_pat}
        )
        open_offers_on_terminal = q6.fetchall()
        if open_offers_on_terminal:
            raise InvariantViolationError(
                f"INVARIANT VIOLATION: no_open_offers_on_terminal_deliveries -> Open offers on terminal deliveries: {open_offers_on_terminal}"
            )

        # 7. Every Non-Pending Order Has Events
        q7 = await session.execute(
            text("""
                SELECT o.id, o.status
                FROM orders o
                JOIN users u ON o.customer_id = u.id
                WHERE u.email LIKE :user_pat
                  AND o.status != 'pending'
                  AND NOT EXISTS (
                      SELECT 1 FROM order_events oe WHERE oe.order_id = o.id
                  )
            """),
            {"user_pat": user_pat}
        )
        orders_without_events = q7.fetchall()
        if orders_without_events:
            raise InvariantViolationError(
                f"INVARIANT VIOLATION: every_non_pending_order_has_events -> Non-pending orders lacking transition events: {orders_without_events}"
            )

        # 8. No Duplicate Transition Events
        q8 = await session.execute(
            text("""
                SELECT oe.order_id, oe.from_state, oe.to_state, COUNT(*)
                FROM order_events oe
                JOIN orders o ON oe.order_id = o.id
                JOIN users u ON o.customer_id = u.id
                WHERE u.email LIKE :user_pat
                GROUP BY oe.order_id, oe.from_state, oe.to_state
                HAVING COUNT(*) > 1
            """),
            {"user_pat": user_pat}
        )
        dup_events = q8.fetchall()
        if dup_events:
            raise InvariantViolationError(
                f"INVARIANT VIOLATION: no_duplicate_transition_events -> Duplicate order event transitions recorded: {dup_events}"
            )

        # 9. Order Totals Equal Items Sum
        q9 = await session.execute(
            text("""
                SELECT o.id, o.total_amount,
                       COALESCE((SELECT SUM(oi.line_total) FROM order_items oi WHERE oi.order_id = o.id), 0) AS calc_total
                FROM orders o
                JOIN users u ON o.customer_id = u.id
                WHERE u.email LIKE :user_pat
                  AND o.total_amount != COALESCE((SELECT SUM(oi.line_total) FROM order_items oi WHERE oi.order_id = o.id), 0)
            """),
            {"user_pat": user_pat}
        )
        math_inconsistencies = q9.fetchall()
        if math_inconsistencies:
            raise InvariantViolationError(
                f"INVARIANT VIOLATION: order_totals_equal_items_plus_fees -> Order total math mismatch: {math_inconsistencies}"
            )

        # 10. No Orphan Rows
        # Check orphan cart items
        q10_a = await session.execute(
            text("SELECT id FROM cart_items WHERE cart_id NOT IN (SELECT id FROM carts)")
        )
        orphan_cart_items = q10_a.fetchall()
        if orphan_cart_items:
            raise InvariantViolationError(
                f"INVARIANT VIOLATION: no_orphan_rows -> Orphan cart items found: {orphan_cart_items}"
            )

        # Check orphan order items
        q10_b = await session.execute(
            text("SELECT id FROM order_items WHERE order_id NOT IN (SELECT id FROM orders)")
        )
        orphan_order_items = q10_b.fetchall()
        if orphan_order_items:
            raise InvariantViolationError(
                f"INVARIANT VIOLATION: no_orphan_rows -> Orphan order items found: {orphan_order_items}"
            )

    await engine.dispose()
