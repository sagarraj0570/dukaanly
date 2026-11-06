import asyncio
from sqlalchemy import text
from app.db.session import async_session_maker

async def check_catalog():
    async with async_session_maker() as s:
        r = await s.execute(text("""
            SELECT sh.name, sh.source_id, sh.is_orderable, sh.verification_status,
                   COUNT(p.id) FILTER (WHERE p.is_active) as active_products,
                   COUNT(p.id) as total_products
            FROM shops sh
            LEFT JOIN products p ON p.shop_id = sh.id
            WHERE sh.source = 'demo'
            GROUP BY sh.id, sh.name, sh.source_id, sh.is_orderable, sh.verification_status
            ORDER BY sh.name
        """))
        rows = r.fetchall()
        for row in rows:
            print(f'{row.name} | orderable={row.is_orderable} | status={row.verification_status} | active={row.active_products} | total={row.total_products}')
        
        total_shops = await s.execute(text("SELECT COUNT(*) FROM shops WHERE source = 'demo'"))
        print(f'\nTotal demo shops: {total_shops.scalar()}')
        
        all_shops = await s.execute(text("SELECT COUNT(*) FROM shops"))
        print(f'Total all shops: {all_shops.scalar()}')
        
        # Check shop locations
        r2 = await s.execute(text("""
            SELECT name, 
                   ST_Y(location::geometry) as lat, 
                   ST_X(location::geometry) as lon,
                   is_orderable,
                   source
            FROM shops 
            WHERE is_active = true
            ORDER BY source, name
        """))
        print('\nAll active shops with coords:')
        for row in r2.fetchall():
            print(f'  {row.source} | {row.name} | lat={row.lat:.4f}, lon={row.lon:.4f} | orderable={row.is_orderable}')

asyncio.run(check_catalog())
