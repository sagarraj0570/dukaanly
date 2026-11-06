"""
System Test Data Cleanup Utility.

Removes all test entities strictly namespaced under a specific RUN_ID,
or all historical leftover 'SYSTEST' data from crashed runs, respecting
foreign key constraints in deterministic dependency order.

Usage:
    python -m tests_system.cleanup --all-systest
    python -m tests_system.cleanup --run-id <RUN_ID>
"""

import sys
import argparse
import asyncio
import logging
from typing import Optional, List

from sqlalchemy import text, bindparam
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from tests_system.config import ASYNC_DB_URL, RUN_ID

logger = logging.getLogger("tests_system.cleanup")


async def cleanup_systest_data(run_id: Optional[str] = None, all_systest: bool = False) -> dict:
    """
    Deletes namespaced system test entities in topological dependency order.
    If all_systest is True, deletes all entities matching 'systest-%' or 'SYSTEST %'.
    If run_id is supplied, deletes only entities matching that specific run_id.
    """
    engine = create_async_engine(ASYNC_DB_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    counts = {
        "order_events": 0,
        "delivery_offers": 0,
        "inventory_reservations": 0,
        "payments": 0,
        "order_items": 0,
        "deliveries": 0,
        "orders": 0,
        "cart_items": 0,
        "carts": 0,
        "inventory": 0,
        "products": 0,
        "shops": 0,
        "rider_profiles": 0,
        "refresh_tokens": 0,
        "users": 0,
    }

    if not run_id and not all_systest:
        run_id = RUN_ID

    pattern_email = f"systest-{run_id}-%" if not all_systest else "systest-%"
    pattern_shop = f"SYSTEST {run_id}%" if not all_systest else "SYSTEST %"

    async with session_maker() as session:
        # 1. Identify target user IDs and shop IDs
        user_rows = (await session.execute(
            text("SELECT id FROM users WHERE email LIKE :pat"),
            {"pat": pattern_email}
        )).fetchall()
        user_ids = [str(r[0]) for r in user_rows]

        shop_rows = (await session.execute(
            text("SELECT id FROM shops WHERE name LIKE :pat"),
            {"pat": pattern_shop}
        )).fetchall()
        shop_ids = [str(r[0]) for r in shop_rows]

        if not user_ids and not shop_ids:
            await engine.dispose()
            return counts

        # Helper to format SQL array parameter safely
        u_list = list(user_ids) if user_ids else ["00000000-0000-0000-0000-000000000000"]
        s_list = list(shop_ids) if shop_ids else ["00000000-0000-0000-0000-000000000000"]

        # 2. Identify associated order IDs and delivery IDs
        order_rows = (await session.execute(
            text("SELECT id FROM orders WHERE customer_id IN :u_list OR shop_id IN :s_list").bindparams(
                bindparam("u_list", expanding=True), bindparam("s_list", expanding=True)
            ),
            {"u_list": u_list, "s_list": s_list}
        )).fetchall()
        order_ids = [str(r[0]) for r in order_rows] if order_rows else ["00000000-0000-0000-0000-000000000000"]

        delivery_rows = (await session.execute(
            text("SELECT id FROM deliveries WHERE order_id IN :o_list").bindparams(
                bindparam("o_list", expanding=True)
            ),
            {"o_list": order_ids}
        )).fetchall()
        delivery_ids = [str(r[0]) for r in delivery_rows] if delivery_rows else ["00000000-0000-0000-0000-000000000000"]

        # 3. Cascade deletions in reverse foreign-key order
        # a. Order events
        res = await session.execute(
            text("DELETE FROM order_events WHERE order_id IN :o_list").bindparams(
                bindparam("o_list", expanding=True)
            ),
            {"o_list": order_ids}
        )
        counts["order_events"] = res.rowcount

        # b. Delivery offers
        res = await session.execute(
            text("DELETE FROM delivery_offers WHERE delivery_id IN :d_list").bindparams(
                bindparam("d_list", expanding=True)
            ),
            {"d_list": delivery_ids}
        )
        counts["delivery_offers"] = res.rowcount

        # c. Inventory reservations
        res = await session.execute(
            text("DELETE FROM inventory_reservations WHERE order_id IN :o_list").bindparams(
                bindparam("o_list", expanding=True)
            ),
            {"o_list": order_ids}
        )
        counts["inventory_reservations"] = res.rowcount

        # d. Payments
        res = await session.execute(
            text("DELETE FROM payments WHERE order_id IN :o_list").bindparams(
                bindparam("o_list", expanding=True)
            ),
            {"o_list": order_ids}
        )
        counts["payments"] = res.rowcount

        # e. Order items
        res = await session.execute(
            text("DELETE FROM order_items WHERE order_id IN :o_list").bindparams(
                bindparam("o_list", expanding=True)
            ),
            {"o_list": order_ids}
        )
        counts["order_items"] = res.rowcount

        # f. Deliveries
        res = await session.execute(
            text("DELETE FROM deliveries WHERE order_id IN :o_list").bindparams(
                bindparam("o_list", expanding=True)
            ),
            {"o_list": order_ids}
        )
        counts["deliveries"] = res.rowcount

        # g. Orders
        res = await session.execute(
            text("DELETE FROM orders WHERE id IN :o_list").bindparams(
                bindparam("o_list", expanding=True)
            ),
            {"o_list": order_ids}
        )
        counts["orders"] = res.rowcount

        # h. Cart items & Carts
        res = await session.execute(
            text("DELETE FROM cart_items WHERE cart_id IN (SELECT id FROM carts WHERE customer_id IN :u_list)").bindparams(
                bindparam("u_list", expanding=True)
            ),
            {"u_list": u_list}
        )
        counts["cart_items"] = res.rowcount

        res = await session.execute(
            text("DELETE FROM carts WHERE customer_id IN :u_list OR shop_id IN :s_list").bindparams(
                bindparam("u_list", expanding=True), bindparam("s_list", expanding=True)
            ),
            {"u_list": u_list, "s_list": s_list}
        )
        counts["carts"] = res.rowcount

        # i. Inventory & Products
        prod_rows = (await session.execute(
            text("SELECT id FROM products WHERE shop_id IN :s_list").bindparams(
                bindparam("s_list", expanding=True)
            ),
            {"s_list": s_list}
        )).fetchall()
        prod_ids = [str(r[0]) for r in prod_rows] if prod_rows else ["00000000-0000-0000-0000-000000000000"]

        res = await session.execute(
            text("DELETE FROM inventory WHERE product_id IN :p_list").bindparams(
                bindparam("p_list", expanding=True)
            ),
            {"p_list": prod_ids}
        )
        counts["inventory"] = res.rowcount

        res = await session.execute(
            text("DELETE FROM products WHERE shop_id IN :s_list").bindparams(
                bindparam("s_list", expanding=True)
            ),
            {"s_list": s_list}
        )
        counts["products"] = res.rowcount

        # j. Shops
        res = await session.execute(
            text("DELETE FROM shops WHERE id IN :s_list").bindparams(
                bindparam("s_list", expanding=True)
            ),
            {"s_list": s_list}
        )
        counts["shops"] = res.rowcount

        # k. Rider Profiles
        res = await session.execute(
            text("DELETE FROM rider_profiles WHERE user_id IN :u_list").bindparams(
                bindparam("u_list", expanding=True)
            ),
            {"u_list": u_list}
        )
        counts["rider_profiles"] = res.rowcount

        # l. Refresh Tokens
        res = await session.execute(
            text("DELETE FROM refresh_tokens WHERE user_id IN :u_list").bindparams(
                bindparam("u_list", expanding=True)
            ),
            {"u_list": u_list}
        )
        counts["refresh_tokens"] = res.rowcount

        # m. Notifications
        await session.execute(
            text("DELETE FROM notifications WHERE user_id IN :u_list").bindparams(
                bindparam("u_list", expanding=True)
            ),
            {"u_list": u_list}
        )

        # m. Users
        res = await session.execute(
            text("DELETE FROM users WHERE id IN :u_list").bindparams(
                bindparam("u_list", expanding=True)
            ),
            {"u_list": u_list}
        )
        counts["users"] = res.rowcount

        await session.commit()

    await engine.dispose()
    return counts


def main():
    parser = argparse.ArgumentParser(description="Clean up namespaced Dukaanly system test entities.")
    parser.add_argument("--all-systest", action="store_true", help="Delete all leftover 'systest-*' entities.")
    parser.add_argument("--run-id", type=str, default=None, help="Delete entities for a specific RUN_ID.")
    args = parser.parse_args()

    target = "ALL leftover SYSTEST data" if args.all_systest else f"RUN_ID={args.run_id or RUN_ID}"
    print(f"Cleaning up {target}...")
    counts = asyncio.run(cleanup_systest_data(run_id=args.run_id, all_systest=args.all_systest))
    print("Deleted rows:")
    for table, count in counts.items():
        if count > 0:
            print(f"  {table}: {count}")
    print("Cleanup completed successfully.")


if __name__ == "__main__":
    main()
