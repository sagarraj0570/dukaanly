import asyncio
from decimal import Decimal
from sqlalchemy import select
from geoalchemy2.elements import WKTElement
from app.db.session import async_session_maker
from app.models.user import User, UserRole
from app.models.shop import Shop
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.rider import RiderProfile
from app.core.security import get_password_hash

DEMO_PASSWORD = "Password123!"

DEMO_USERS = [
    {
        "name": "Rahul Sharma (Customer)",
        "email": "customer@dukaanly.com",
        "phone_number": "9876543210",
        "role": UserRole.customer,
    },
    {
        "name": "Ramesh Kirana (Shop Owner)",
        "email": "shop@dukaanly.com",
        "phone_number": "9876543211",
        "role": UserRole.shop_owner,
    },
    {
        "name": "Amit Kumar (Rider)",
        "email": "rider@dukaanly.com",
        "phone_number": "9876543212",
        "role": UserRole.rider,
    },
]

DEMO_PRODUCTS = [
    {"name": "Aashirvaad Whole Wheat Atta 5kg", "category": "Groceries", "price": Decimal("245.00"), "stock": 50},
    {"name": "Amul Taaza Homogenised Toned Milk 1L", "category": "Dairy", "price": Decimal("72.00"), "stock": 100},
    {"name": "Tata Salt Vacuum Evaporated 1kg", "category": "Groceries", "price": Decimal("28.00"), "stock": 200},
    {"name": "Fortune Sunlite Refined Sunflower Oil 1L", "category": "Edible Oils", "price": Decimal("145.00"), "stock": 40},
    {"name": "Maggi 2-Minute Instant Noodles 280g", "category": "Snacks", "price": Decimal("58.00"), "stock": 75},
]

async def seed_demo_data():
    async with async_session_maker() as session:
        # 1. Seed or update demo users
        users = {}
        for user_data in DEMO_USERS:
            stmt = select(User).where(User.email == user_data["email"])
            res = await session.execute(stmt)
            user = res.scalar_one_or_none()
            if not user:
                user = User(
                    name=user_data["name"],
                    email=user_data["email"],
                    phone_number=user_data["phone_number"],
                    password_hash=get_password_hash(DEMO_PASSWORD),
                    role=user_data["role"],
                    is_active=True,
                )
                session.add(user)
                await session.flush()
                print(f"Created demo user: {user.email} (Role: {user.role.value})")
            else:
                user.password_hash = get_password_hash(DEMO_PASSWORD)
                user.is_active = True
                user.role = user_data["role"]
                print(f"Updated demo user: {user.email}")
            users[user_data["email"]] = user

        # 2. Seed shop for shop_owner
        owner = users["shop@dukaanly.com"]
        stmt = select(Shop).where(Shop.owner_id == owner.id)
        res = await session.execute(stmt)
        shop = res.scalar_one_or_none()
        if not shop:
            shop = Shop(
                owner_id=owner.id,
                name="Sharma Kirana & General Store",
                description="Fresh groceries, daily dairy essentials, staples, and FMCG items delivered in 15 minutes.",
                location=WKTElement("POINT(77.5946 12.9716)", srid=4326),
                address="12 MG Road, Brigade Junction, Bengaluru 560001",
                is_active=True,
            )
            session.add(shop)
            await session.flush()
            print(f"Created demo shop: {shop.name}")

        # 3. Seed products for shop
        for prod_data in DEMO_PRODUCTS:
            stmt = select(Product).where(Product.shop_id == shop.id, Product.name == prod_data["name"])
            res = await session.execute(stmt)
            product = res.scalar_one_or_none()
            if not product:
                product = Product(
                    shop_id=shop.id,
                    name=prod_data["name"],
                    category=prod_data["category"],
                    price=prod_data["price"],
                    description=f"Fresh and genuine {prod_data['name']}",
                    is_active=True,
                )
                session.add(product)
                await session.flush()
                
                inventory = Inventory(
                    product_id=product.id,
                    stock=prod_data["stock"],
                    version=1,
                )
                session.add(inventory)
                print(f"Created demo product: {product.name} (Stock: {prod_data['stock']})")

        # 4. Seed rider profile
        rider = users["rider@dukaanly.com"]
        stmt = select(RiderProfile).where(RiderProfile.user_id == rider.id)
        res = await session.execute(stmt)
        rider_profile = res.scalar_one_or_none()
        if not rider_profile:
            rider_profile = RiderProfile(
                user_id=rider.id,
                is_available=True,
                location=WKTElement("POINT(77.5950 12.9720)", srid=4326),
            )
            session.add(rider_profile)
            print("Created demo rider profile for Amit Kumar")
        else:
            rider_profile.is_available = True
            rider_profile.location = WKTElement("POINT(77.5950 12.9720)", srid=4326)

        await session.commit()
        print("\nAll demo accounts and catalog data successfully seeded!")

if __name__ == "__main__":
    asyncio.run(seed_demo_data())
