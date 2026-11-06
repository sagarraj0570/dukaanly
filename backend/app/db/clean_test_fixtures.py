import asyncio
from sqlalchemy import select, delete
from app.db.session import async_session_maker
from app.models.shop import Shop
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.order import Order, OrderItem
from app.models.delivery import Delivery
from app.models.payment import Payment
from app.models.cart import CartItem

async def clean_test_fixtures():
    async with async_session_maker() as session:
        print("Cleaning up remaining test fixture shops...")
        
        stmt = select(Shop.id, Shop.name).where(
            Shop.name.in_([
                "Inactive Kirana", "WS Shop", "Broadcast Shop"
            ])
            | Shop.name.like("Claimed Protection Store%")
            | Shop.name.ilike("SYSTEST%")
            | Shop.name.ilike("%(Test)%")
            | Shop.name.ilike("%[Test]%")
            | Shop.name.like("st\\_%")
            | Shop.description.ilike("%system test%")
        )
        res = await session.execute(stmt)
        test_shops = res.all()
        print(f"Found {len(test_shops)} additional test fixture shops to clean.")
        
        shop_ids = [s[0] for s in test_shops]
        if shop_ids:
            deliv_orders_stmt = select(Order.id).where(Order.shop_id.in_(shop_ids))
            deliv_orders_res = await session.execute(deliv_orders_stmt)
            order_ids = deliv_orders_res.scalars().all()
            if order_ids:
                await session.execute(delete(Delivery).where(Delivery.order_id.in_(order_ids)))
                await session.execute(delete(Payment).where(Payment.order_id.in_(order_ids)))
                await session.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
                await session.execute(delete(Order).where(Order.id.in_(order_ids)))

            prods_stmt = select(Product.id).where(Product.shop_id.in_(shop_ids))
            prod_ids = (await session.execute(prods_stmt)).scalars().all()
            if prod_ids:
                await session.execute(delete(CartItem).where(CartItem.product_id.in_(prod_ids)))
                await session.execute(delete(Inventory).where(Inventory.product_id.in_(prod_ids)))
                await session.execute(delete(Product).where(Product.id.in_(prod_ids)))

            await session.execute(delete(Shop).where(Shop.id.in_(shop_ids)))
            await session.commit()
            print(f"Successfully deleted {len(shop_ids)} additional test fixture shops.")

        # Re-check remaining verified shops
        remaining = (await session.execute(select(Shop.name, Shop.address, Shop.verification_status, Shop.is_orderable))).all()
        print(f"Remaining shops in database: {len(remaining)}")
        for r in remaining:
            if r[2].value == "verified":
                print(f"  * Verified: {r[0]} ({r[1]})")

if __name__ == '__main__':
    asyncio.run(clean_test_fixtures())
