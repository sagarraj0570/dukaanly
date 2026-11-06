"""
Idempotent Seeding Engine for Dukaanly Realistic Demo Data.

Populates dedicated demo partner shops, realistic product catalogs across 8 core categories,
and verified directory listings in development environments.

Usage:
    python -m app.db.seed_demo
    python -m app.db.seed_demo --reset-stock
"""

import argparse
import asyncio
import logging
import re
from decimal import Decimal
from typing import Dict, Any, Optional

from sqlalchemy import func, select
from geoalchemy2.elements import WKTElement

from app.db.session import async_session_maker
from app.models.user import User
from app.models.shop import Shop, ShopVerificationStatus
from app.models.product import Product
from app.models.master_catalog import MasterCatalogItem
from app.models.inventory import Inventory
from app.models.rider import RiderProfile
from app.core.security import get_password_hash
from app.core.config import settings
from app.db.demo_catalog import (
    DEMO_PASSWORD,
    DEMO_USERS,
    DEMO_SHOPS,
    DEMO_PRODUCTS,
)

logger = logging.getLogger("seed_demo")
_UNSET = object()


def shop_data_category(source_id: str) -> str:
    """Return the configured demo category for reporting without querying external data."""
    for shop in DEMO_SHOPS:
        if shop["source_id"] == source_id:
            return str(shop.get("category", "general"))
    return "general"


def verify_seed_environment(env: object = _UNSET) -> bool:
    """
    Verify that the current environment permits seeding demo accounts and catalogs.
    Demo accounts and default credentials are strictly restricted to APP_ENV='development'.
    Raises RuntimeError if the environment is missing, ambiguous, staging, or production.
    """
    current_env = env if env is not _UNSET else getattr(settings, "APP_ENV", None)
    if not current_env or not isinstance(current_env, str):
        raise RuntimeError(
            "Demo seeding aborted: APP_ENV is missing or empty. "
            "Demo accounts and default credentials may ONLY be seeded when APP_ENV='development'."
        )

    normalized_env = current_env.strip().lower()
    if normalized_env != "development":
        raise RuntimeError(
            f"Demo seeding aborted: forbidden in environment '{current_env}'. "
            "Staging and production environments must never automatically create or reset "
            "demo accounts with default credentials."
        )
    return True


async def seed_demo_data(reset_stock: bool = False) -> Dict[str, Any]:
    """
    Seed or update demo accounts, partner shops, inventory, and directory POIs idempotently.
    
    If reset_stock is True, existing demo products will have their stock levels reset
    to their initial catalog values and inventory versions incremented.
    """
    verify_seed_environment()

    stats: Dict[str, Any] = {
        "users_created": 0,
        "users_updated": 0,
        "shops_created": 0,
        "shops_updated": 0,
        "products_created": 0,
        "products_updated": 0,
        "inventory_reset": 0,
    }

    async with async_session_maker() as session:
        # ── 1. Seed or update demo users ──────────────────────────────────────
        users: Dict[str, User] = {}
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
                stats["users_created"] += 1
                print(f"Created demo user: {user.email} (Role: {user.role.value})")
            else:
                user.name = user_data["name"]
                user.phone_number = user_data["phone_number"]
                user.password_hash = get_password_hash(DEMO_PASSWORD)
                user.is_active = True
                user.role = user_data["role"]
                stats["users_updated"] += 1
                print(f"Updated demo user: {user.email}")
            users[user_data["email"]] = user

        # ── 2. Seed or update dedicated demo shops ────────────────────────────
        seeded_shops: Dict[str, Shop] = {}
        for shop_data in DEMO_SHOPS:
            owner = users.get(shop_data["owner_email"])
            if not owner:
                continue

            source_id = shop_data["source_id"]
            # Look up shop by source_id first, then fallback to owner_id
            stmt = select(Shop).where(Shop.source_id == source_id)
            res = await session.execute(stmt)
            shop = res.scalars().first()

            if not shop:
                # Also check by owner_id for backward compatibility
                stmt = select(Shop).where(Shop.owner_id == owner.id)
                res = await session.execute(stmt)
                shop = res.scalars().first()

            point_wkt = f"POINT({shop_data['longitude']} {shop_data['latitude']})"

            if not shop:
                shop = Shop(
                    owner_id=owner.id,
                    name=shop_data["name"],
                    description=shop_data["description"],
                    location=WKTElement(point_wkt, srid=4326),
                    address=shop_data["address"],
                    phone=shop_data.get("phone"),
                    opening_hours=shop_data.get("opening_hours"),
                    is_active=shop_data["is_active"],
                    is_orderable=shop_data["is_orderable"],
                    verification_status=shop_data["verification_status"],
                    source=shop_data["source"],
                    source_id=source_id,
                    source_attribution=shop_data["source_attribution"],
                )
                session.add(shop)
                await session.flush()
                stats["shops_created"] += 1
                print(f"Created demo partner shop: {shop.name}")
            else:
                shop.owner_id = owner.id
                shop.name = shop_data["name"]
                shop.description = shop_data["description"]
                shop.address = shop_data["address"]
                shop.phone = shop_data.get("phone")
                shop.opening_hours = shop_data.get("opening_hours")
                shop.location = WKTElement(point_wkt, srid=4326)
                shop.is_active = shop_data["is_active"]
                shop.is_orderable = shop_data["is_orderable"]
                shop.verification_status = shop_data["verification_status"]
                shop.source = shop_data["source"]
                shop.source_id = source_id
                shop.source_attribution = shop_data["source_attribution"]
                stats["shops_updated"] += 1
                print(f"Updated demo partner shop: {shop.name}")

            seeded_shops[source_id] = shop

        # ── 3. Seed realistic product catalogs & inventory ────────────────────
        for source_id, product_list in DEMO_PRODUCTS.items():
            shop = seeded_shops.get(source_id)
            if not shop:
                continue

            for prod_data in product_list:
                stmt = select(Product).where(
                    Product.shop_id == shop.id,
                    Product.name == prod_data["name"]
                )
                res = await session.execute(stmt)
                product = res.scalar_one_or_none()

                norm_name = re.sub(r"\[dukaanly demo product\]", "", prod_data["name"].lower().strip(), flags=re.I).strip()
                master_stmt = select(MasterCatalogItem).where(MasterCatalogItem.normalized_name == norm_name)
                master_item = (await session.execute(master_stmt)).scalar_one_or_none()

                if not product:
                    product = Product(
                        shop_id=shop.id,
                        name=prod_data["name"],
                        category=prod_data["category"],
                        price=prod_data["price"],
                        description=prod_data["description"],
                        image_url=master_item.image_url if master_item else prod_data.get("image_url"),
                        thumb_url=master_item.thumb_url if master_item else None,
                        image_source=master_item.image_source if master_item else None,
                        image_license=master_item.image_license if master_item else None,
                        image_attribution=master_item.image_attribution if master_item else None,
                        image_source_url=master_item.image_source_url if master_item else None,
                        image_match_confidence=master_item.image_match_confidence if master_item else None,
                        image_reviewed=master_item.image_reviewed if master_item else False,
                        master_item_id=master_item.id if master_item else None,
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
                    stats["products_created"] += 1
                else:
                    product.category = prod_data["category"]
                    product.price = prod_data["price"]
                    product.description = prod_data["description"]
                    product.is_active = True
                    if master_item:
                        product.master_item_id = master_item.id
                        if not product.custom_image_url:
                            product.image_url = master_item.image_url
                            product.thumb_url = master_item.thumb_url
                            product.image_source = master_item.image_source
                            product.image_license = master_item.image_license
                            product.image_attribution = master_item.image_attribution
                            product.image_source_url = master_item.image_source_url
                            product.image_match_confidence = master_item.image_match_confidence
                            product.image_reviewed = master_item.image_reviewed
                    elif not product.image_url:
                        product.image_url = prod_data.get("image_url")

                    stats["products_updated"] += 1

                    # Check or reset inventory
                    inv_stmt = select(Inventory).where(Inventory.product_id == product.id)
                    inv_res = await session.execute(inv_stmt)
                    inventory = inv_res.scalar_one_or_none()

                    if not inventory:
                        inventory = Inventory(
                            product_id=product.id,
                            stock=prod_data["stock"],
                            version=1,
                        )
                        session.add(inventory)
                    elif reset_stock:
                        inventory.stock = prod_data["stock"]
                        inventory.version += 1
                        stats["inventory_reset"] += 1

            # Retire legacy products that are no longer in the catalog; ensure fallback image
            catalog_product_names = {p["name"] for p in product_list}
            existing_shop_prods = (await session.execute(
                select(Product).where(Product.shop_id == shop.id)
            )).scalars().all()
            for ep in existing_shop_prods:
                if ep.name not in catalog_product_names:
                    ep.is_active = False
                # Strip legacy "[Dukaanly Demo Product]" prefix if present (dev-only tag, never shown to users)
                if ep.description and ep.description.startswith("[Dukaanly Demo Product] "):
                    ep.description = ep.description[len("[Dukaanly Demo Product] "):]
                if not ep.image_url:
                    ep.image_url = "https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=600&q=80"

        print(
            f"\nProducts Summary: {stats['products_created']} created, "
            f"{stats['products_updated']} updated, {stats['inventory_reset']} stock reset."
        )

        # ── 4. Seed rider profile in Boring Road, Patna ───────────────────────
        rider = users.get("rider@dukaanly.com")
        if rider:
            stmt = select(RiderProfile).where(RiderProfile.user_id == rider.id)
            res = await session.execute(stmt)
            rider_profile = res.scalar_one_or_none()
            if not rider_profile:
                rider_profile = RiderProfile(
                    user_id=rider.id,
                    is_available=True,
                    location=WKTElement("POINT(85.1160 25.6146)", srid=4326),
                )
                session.add(rider_profile)
                print("Created demo rider profile for Amit Kumar in Patna")
            else:
                rider_profile.is_available = True
                rider_profile.location = WKTElement("POINT(85.1160 25.6146)", srid=4326)
                print("Relocated demo rider Amit Kumar to Boring Road, Patna")

        await session.commit()

        # Directory listings deliberately are not imported as part of demo seeding.
        # Public-source imports are network- and provenance-sensitive operations that
        # must be run explicitly through ``app.cli.import_merchants``.
        inventory_report = []
        for source_id, shop in seeded_shops.items():
            product_count = (
                await session.execute(
                    select(func.count(Product.id)).where(
                        Product.shop_id == shop.id,
                        Product.is_active.is_(True),
                    )
                )
            ).scalar_one()
            inventory_count = (
                await session.execute(
                    select(func.count(Inventory.id))
                    .join(Product, Inventory.product_id == Product.id)
                    .where(Product.shop_id == shop.id, Product.is_active.is_(True))
                )
            ).scalar_one()
            inventory_report.append({
                "source_id": source_id,
                "shop": shop.name,
                "category": shop_data_category(source_id),
                "distinct_active_products": product_count,
                "inventory_records": inventory_count,
                "meets_50_product_minimum": product_count >= 50 and inventory_count >= 50,
            })

        stats["inventory_report"] = inventory_report
        print("\nAll demo accounts, partner shops, and inventory are ready.")
        print("Directory listings are imported separately: python -m app.cli.import_merchants --provider curated")
        for row in inventory_report:
            print(
                f"  - {row['shop']} ({row['category']}): "
                f"{row['distinct_active_products']} products, {row['inventory_records']} inventory records, "
                f"minimum met={row['meets_50_product_minimum']}"
            )
        return stats


def main():
    parser = argparse.ArgumentParser(description="Seed Dukaanly realistic demo catalog.")
    parser.add_argument(
        "--reset-stock",
        action="store_true",
        help="Reset existing demo product stock back to original catalog values.",
    )
    args = parser.parse_args()

    verify_seed_environment()
    asyncio.run(seed_demo_data(reset_stock=args.reset_stock))


if __name__ == "__main__":
    main()
