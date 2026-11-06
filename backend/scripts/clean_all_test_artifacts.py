import sys
import os
sys.path.insert(0, os.path.abspath('backend'))
import asyncio
from sqlalchemy import text
from app.db.session import async_session_maker

async def clean_all_test_artifacts():
    async with async_session_maker() as db:
        print("=== IDENTIFYING TEST ARTIFACTS IN DB ===")
        
        # 1. Test shops
        res_shops = await db.execute(text("""
            SELECT id, name FROM shops 
            WHERE name ILIKE 'SYSTEST%' 
               OR name ILIKE '%(Test)%' 
               OR name ILIKE '%[Test]%' 
               OR name ILIKE 'st\\_%' ESCAPE '\\' 
               OR description ILIKE '%system test%'
               OR description ILIKE '%for run st\\_%' ESCAPE '\\'
        """))
        test_shops = res_shops.fetchall()
        print(f"Found {len(test_shops)} test shops:")
        for s in test_shops:
            print(f"  - {s[0]}: {s[1]}")
            
        shop_ids = [str(s[0]) for s in test_shops]

        # 2. Test users (Strict patterns so demo users like Rahul Sharma are never touched)
        res_users = await db.execute(text("""
            SELECT id, name, email FROM users 
            WHERE email ILIKE 'systest-%' 
               OR email ILIKE '%st\_%@dukaanly.com' ESCAPE '\\'
               OR name LIKE 'Shop Owner st_%'
               OR name LIKE 'Rider st_%'
               OR name LIKE 'SYSTEST%'
        """))
        test_users = res_users.fetchall()
        print(f"Found {len(test_users)} test users:")
        for u in test_users:
            print(f"  - {u[0]}: {u[1]} ({u[2]})")
            
        user_ids = [str(u[0]) for u in test_users]
        
        # 3. Test products (like 'Unverified Product Item' or transient test products)
        res_trans_prods = await db.execute(text("""
            SELECT id, name FROM products 
            WHERE name ILIKE 'Unverified Product Item%' 
               OR name ILIKE '%(Test)%'
        """))
        trans_prods = res_trans_prods.fetchall()
        trans_prod_ids = [str(p[0]) for p in trans_trans_prods.fetchall()] if False else [str(p[0]) for p in trans_prods]
        print(f"Found {len(trans_prod_ids)} transient test products directly in DB.")

        print("\n=== PURGING TEST ARTIFACTS ===")
        shop_id_list = "('" + "','".join(shop_ids) + "')" if shop_ids else None
        user_id_list = "('" + "','".join(user_ids) + "')" if user_ids else None
        trans_prod_list = "('" + "','".join(trans_prod_ids) + "')" if trans_prod_ids else None

        # Delete orders associated with test shops or test users
        if shop_id_list or user_id_list:
            conds = []
            if shop_id_list:
                conds.append(f"shop_id IN {shop_id_list}")
            if user_id_list:
                conds.append(f"customer_id IN {user_id_list}")
            where_clause = " OR ".join(conds)

            res_orders = await db.execute(text(f"SELECT id FROM orders WHERE {where_clause}"))
            order_ids = [str(r[0]) for r in res_orders.fetchall()]
            
            if order_ids:
                order_id_list = "('" + "','".join(order_ids) + "')"
                print(f"Deleting data for {len(order_ids)} test orders...")
                await db.execute(text(f"DELETE FROM order_events WHERE order_id IN {order_id_list}"))
                await db.execute(text(f"DELETE FROM inventory_reservations WHERE order_id IN {order_id_list}"))
                await db.execute(text(f"DELETE FROM payments WHERE order_id IN {order_id_list}"))
                
                res_delivs = await db.execute(text(f"SELECT id FROM deliveries WHERE order_id IN {order_id_list}"))
                deliv_ids = [str(r[0]) for r in res_delivs.fetchall()]
                if deliv_ids:
                    deliv_id_list = "('" + "','".join(deliv_ids) + "')"
                    await db.execute(text(f"DELETE FROM delivery_offers WHERE delivery_id IN {deliv_id_list}"))
                
                await db.execute(text(f"DELETE FROM deliveries WHERE order_id IN {order_id_list}"))
                await db.execute(text(f"DELETE FROM order_items WHERE order_id IN {order_id_list}"))
                await db.execute(text(f"DELETE FROM orders WHERE id IN {order_id_list}"))

        # Delete transient test products
        if trans_prod_list:
            print(f"Deleting {len(trans_prod_ids)} transient test products...")
            await db.execute(text(f"DELETE FROM cart_items WHERE product_id IN {trans_prod_list}"))
            await db.execute(text(f"DELETE FROM inventory WHERE product_id IN {trans_prod_list}"))
            await db.execute(text(f"DELETE FROM order_items WHERE product_id IN {trans_prod_list}"))
            await db.execute(text(f"DELETE FROM products WHERE id IN {trans_prod_list}"))

        # Delete products and inventory for test shops
        if shop_id_list:
            print(f"Deleting products and inventory for {len(shop_ids)} test shops...")
            res_prods = await db.execute(text(f"SELECT id FROM products WHERE shop_id IN {shop_id_list}"))
            prod_ids = [str(r[0]) for r in res_prods.fetchall()]
            if prod_ids:
                prod_id_list = "('" + "','".join(prod_ids) + "')"
                await db.execute(text(f"DELETE FROM cart_items WHERE product_id IN {prod_id_list}"))
                await db.execute(text(f"DELETE FROM inventory WHERE product_id IN {prod_id_list}"))
                await db.execute(text(f"DELETE FROM order_items WHERE product_id IN {prod_id_list}"))
                await db.execute(text(f"DELETE FROM products WHERE id IN {prod_id_list}"))
            
            # Delete carts for test shops
            await db.execute(text(f"DELETE FROM cart_items WHERE cart_id IN (SELECT id FROM carts WHERE shop_id IN {shop_id_list})"))
            await db.execute(text(f"DELETE FROM carts WHERE shop_id IN {shop_id_list}"))
            
            # Delete test shops
            await db.execute(text(f"DELETE FROM shops WHERE id IN {shop_id_list}"))
            print(f"Deleted {len(shop_ids)} test shops.")
            
        # Delete test users
        if user_id_list:
            print(f"Deleting {len(user_ids)} test users...")
            await db.execute(text(f"DELETE FROM delivery_offers WHERE rider_id IN (SELECT id FROM rider_profiles WHERE user_id IN {user_id_list})"))
            await db.execute(text(f"DELETE FROM rider_profiles WHERE user_id IN {user_id_list}"))
            await db.execute(text(f"DELETE FROM refresh_tokens WHERE user_id IN {user_id_list}"))
            await db.execute(text(f"DELETE FROM notifications WHERE user_id IN {user_id_list}"))
            await db.execute(text(f"DELETE FROM cart_items WHERE cart_id IN (SELECT id FROM carts WHERE customer_id IN {user_id_list})"))
            await db.execute(text(f"DELETE FROM carts WHERE customer_id IN {user_id_list}"))
            await db.execute(text(f"DELETE FROM users WHERE id IN {user_id_list}"))
            print(f"Deleted {len(user_ids)} test users.")

        # Rename edge case sample products to natural, realistic customer-facing names
        print("\n=== RENAMING SAMPLE/EDGE-CASE PRODUCT LABELS IN DB ===")
        await db.execute(text("""
            UPDATE products 
            SET name = 'Catch Kashmiri Chilli Powder 100g', 
                description = 'Authentic Kashmiri red chilli powder giving rich natural color and gentle heat to curries.'
            WHERE name = 'Catch Kashmiri Chilli Powder 100g (Zero Stock Sample)'
        """))
        await db.execute(text("""
            UPDATE products 
            SET name = 'Amul Moti Toned Long Life Milk 450ml', 
                description = 'Homogenised toned long life UHT milk packaged in tamper-evident pouch for daily freshness.'
            WHERE name = 'Amul Moti Toned Long Life Milk 450ml (Low Stock Sample)'
        """))

        await db.commit()
        print("\n=== PURGE & SANITIZATION COMPLETED SUCCESSFULLY ===")
        
        # Verify remaining shops
        res_remain = await db.execute(text("SELECT id, name, verification_status, is_active FROM shops ORDER BY name"))
        rows_remain = res_remain.fetchall()
        print(f"\nRemaining shops in DB ({len(rows_remain)}):")
        for r in rows_remain:
            print(f"  * {r[1]} [{r[2]}, active={r[3]}]")

if __name__ == "__main__":
    asyncio.run(clean_all_test_artifacts())
