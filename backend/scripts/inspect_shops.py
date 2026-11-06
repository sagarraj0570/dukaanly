import asyncio
from app.db.session import async_session_maker
from sqlalchemy import select
from app.models.shop import Shop

async def main():
    async with async_session_maker() as session:
        result = await session.execute(
            select(Shop.id, Shop.name, Shop.is_orderable, Shop.verification_status, Shop.source, Shop.source_id)
        )
        shops = result.fetchall()
        print(f"Total shops in DB: {len(shops)}")
        for s in shops:
            if any(k in s.name.lower() for k in ["home town", "zudio", "tvs", "jalal", "nutrition", "laxhmi"]):
                print("Found match:", s)
            elif s.source != "demo":
                print("Non-demo shop:", s.name, s.source, s.source_id, s.is_orderable, s.verification_status)

if __name__ == "__main__":
    asyncio.run(main())
