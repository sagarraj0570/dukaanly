import uuid
from datetime import datetime, timezone
from typing import Tuple, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, case
from geoalchemy2 import Geography
from geoalchemy2.shape import to_shape
from fastapi import HTTPException, status

from app.models.shop import Shop, ShopVerificationStatus
from app.models.user import User
from app.schemas.shop import ShopCreate, ShopUpdate
from app.services.geoapify import find_cached_discovery_place

async def create_shop(db: AsyncSession, shop_in: ShopCreate, owner: User) -> Shop:
    # We use ST_MakePoint(longitude, latitude)
    point_wkt = f"SRID=4326;POINT({shop_in.location.longitude} {shop_in.location.latitude})"

    db_shop = Shop(
        owner_id=owner.id,
        name=shop_in.name,
        description=shop_in.description,
        address=shop_in.address,
        location=point_wkt,
        is_active=True,
        is_orderable=True,
        verification_status=ShopVerificationStatus.verified,
        source="manual"
    )
    
    db.add(db_shop)
    await db.commit()
    await db.refresh(db_shop)
    return db_shop

async def get_shop_by_id(db: AsyncSession, shop_id: uuid.UUID) -> Shop:
    stmt = select(Shop).where(Shop.id == shop_id)
    result = await db.execute(stmt)
    shop = result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
        
    return shop

async def get_shop_by_id_or_identifier(db: AsyncSession, identifier: str) -> Dict[str, Any] | Shop:
    """
    Look up a shop by UUID, source_id, business name, or cached directory place.
    Supports viewing verified partner shops and discovered neighbourhood stores seamlessly.
    """
    # 1. Try parsing as standard UUID
    try:
        parsed_uuid = uuid.UUID(identifier)
        stmt = select(Shop).where(Shop.id == parsed_uuid)
        result = await db.execute(stmt)
        shop = result.scalar_one_or_none()
        if shop:
            return shop
    except (ValueError, AttributeError):
        pass

    # 2. Check DB by source_id
    stmt = select(Shop).where(Shop.source_id == identifier)
    result = await db.execute(stmt)
    shop = result.scalar_one_or_none()
    if shop:
        return shop

    # 3. Check DB by case-insensitive name match
    stmt = select(Shop).where(Shop.name.ilike(identifier.strip()))
    result = await db.execute(stmt)
    shop = result.scalar_one_or_none()
    if shop:
        return shop

    # 4. Check active Geoapify directory cache (memory/Redis)
    cached_place = await find_cached_discovery_place(identifier)
    if cached_place:
        source_id = cached_place.get("source_id") or identifier
        name = cached_place.get("name") or "Neighbourhood Store"
        category = cached_place.get("category", "Retail")
        det_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, source_id or name)
        now_dt = datetime.now(timezone.utc)
        return {
            "id": det_uuid,
            "owner_id": None,
            "name": name,
            "description": f"{category.capitalize()} store discovered in neighbourhood directory for in-store shopping.",
            "address": cached_place.get("address") or "Patna, Bihar",
            "phone": cached_place.get("phone"),
            "opening_hours": cached_place.get("opening_hours") or "Mon–Sun: 9:00 AM – 9:30 PM",
            "is_active": True,
            "is_orderable": False,
            "verification_status": ShopVerificationStatus.discovered,
            "source": cached_place.get("source", "geoapify"),
            "source_id": source_id,
            "source_attribution": cached_place.get("attribution", "Powered by Geoapify | © OpenStreetMap contributors"),
            "original_url": cached_place.get("website"),
            "import_batch_id": None,
            "imported_at": None,
            "last_seen_at": now_dt,
            "location": {
                "latitude": cached_place.get("latitude", 25.6144),
                "longitude": cached_place.get("longitude", 85.1158)
            },
            "distance_meters": cached_place.get("distance_meters"),
            "is_delivery_eligible": False,
            "delivery_radius_meters": 5000,
            "created_at": now_dt,
            "updated_at": now_dt,
        }

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")

async def get_shop_by_owner_id(db: AsyncSession, owner_id: uuid.UUID) -> Shop | None:
    stmt = select(Shop).where(Shop.owner_id == owner_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def update_shop(db: AsyncSession, shop_id: uuid.UUID, shop_in: ShopUpdate, current_user: User) -> Shop:
    shop = await get_shop_by_id(db, shop_id)
    
    # Ownership isolation
    if shop.owner_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this shop"
        )
        
    update_data = shop_in.model_dump(exclude_unset=True)
    
    if "location" in update_data and update_data["location"]:
        loc = update_data.pop("location")
        shop.location = f"SRID=4326;POINT({loc['longitude']} {loc['latitude']})"
        
    for field, value in update_data.items():
        setattr(shop, field, value)
        
    db.add(shop)
    await db.commit()
    await db.refresh(shop)
    
    return shop

async def get_shops(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    active_only: bool = True,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_meters: int = 5000,
    delivery_only: bool = False,
    verified_only: bool = False,
    include_test: bool = False
) -> Tuple[List[Dict[str, Any]], int]:
    DEFAULT_DELIVERY_RADIUS_METERS = 5000
    PREFERRED_NEARBY_RADIUS_METERS = 3000
    MAX_SEARCH_RADIUS_METERS = 10000

    # Geospatial query when customer coordinates are provided
    if latitude is not None and longitude is not None:
        # Clamp radius between 100 meters and 10,000 meters (10 km)
        clamped_radius = max(100, min(radius_meters, MAX_SEARCH_RADIUS_METERS))

        user_point = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
        user_geog = cast(user_point, Geography())
        shop_geog = cast(Shop.location, Geography())

        dist_expr = func.ST_Distance(shop_geog, user_geog).label("distance_meters")

        stmt = select(Shop, dist_expr).where(Shop.location.is_not(None))
        if active_only:
            stmt = stmt.where(Shop.is_active == True)

        # ST_DWithin on PostGIS geography for accurate ellipsoidal meter distance
        stmt = stmt.where(func.ST_DWithin(shop_geog, user_geog, clamped_radius))

        if delivery_only:
            stmt = stmt.where(Shop.is_orderable == True).where(func.ST_DWithin(shop_geog, user_geog, DEFAULT_DELIVERY_RADIUS_METERS))
        if verified_only:
            stmt = stmt.where(Shop.verification_status == ShopVerificationStatus.verified, Shop.owner_id.is_not(None))
        if not include_test:
            stmt = stmt.where(
                ~Shop.name.ilike("SYSTEST%"),
                ~Shop.name.ilike("%(Test)%"),
                ~Shop.name.ilike("%[Test]%"),
                ~Shop.name.like("st\\_%"),
                ~Shop.description.ilike("%system test%"),
                ~Shop.description.ilike("%for run st\\_%"),
            )

        # Total count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await db.execute(count_stmt)
        total = count_result.scalar_one()

        # Ranking: prefer shops within 3 km in ranking (tier 0), then beyond 3 km (tier 1), ordered by distance ascending
        tier_expr = case((dist_expr <= PREFERRED_NEARBY_RADIUS_METERS, 0), else_=1)
        stmt = stmt.order_by(tier_expr.asc(), dist_expr.asc(), Shop.id.asc()).offset((page - 1) * size).limit(size)
        result = await db.execute(stmt)
        rows = result.all()

        items: List[Dict[str, Any]] = []
        for shop_obj, dist in rows:
            point = to_shape(shop_obj.location)
            dist_float = round(float(dist), 1)
            is_deliv = (dist_float <= float(DEFAULT_DELIVERY_RADIUS_METERS)) if shop_obj.is_orderable else False
            items.append({
                "id": shop_obj.id,
                "owner_id": shop_obj.owner_id,
                "name": shop_obj.name,
                "description": shop_obj.description,
                "address": shop_obj.address,
                "phone": shop_obj.phone,
                "opening_hours": shop_obj.opening_hours,
                "is_active": shop_obj.is_active,
                "is_orderable": shop_obj.is_orderable,
                "verification_status": shop_obj.verification_status,
                "source": shop_obj.source,
                "source_id": shop_obj.source_id,
                "source_attribution": shop_obj.source_attribution,
                "original_url": shop_obj.original_url,
                "import_batch_id": shop_obj.import_batch_id,
                "imported_at": shop_obj.imported_at,
                "last_seen_at": shop_obj.last_seen_at,
                "created_at": shop_obj.created_at,
                "updated_at": shop_obj.updated_at,
                "location": {"latitude": point.y, "longitude": point.x},
                "distance_meters": dist_float,
                "is_delivery_eligible": is_deliv,
                "delivery_radius_meters": DEFAULT_DELIVERY_RADIUS_METERS
            })

        return items, total

    # Standard query when no coordinates are provided
    stmt = select(Shop)
    if active_only:
        stmt = stmt.where(Shop.is_active == True)
    if delivery_only:
        stmt = stmt.where(Shop.is_orderable == True)
    if verified_only:
        stmt = stmt.where(Shop.verification_status == ShopVerificationStatus.verified, Shop.owner_id.is_not(None))
    if not include_test:
        stmt = stmt.where(
            ~Shop.name.ilike("SYSTEST%"),
            ~Shop.name.ilike("%(Test)%"),
            ~Shop.name.ilike("%[Test]%"),
            ~Shop.name.like("st\\_%"),
            ~Shop.description.ilike("%system test%"),
            ~Shop.description.ilike("%for run st\\_%"),
        )
        
    count_stmt = select(func.count()).select_from(stmt.subquery())
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()
    
    stmt = stmt.order_by(Shop.created_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    shops = result.scalars().all()
    
    items: List[Dict[str, Any]] = []
    for s in shops:
        point = to_shape(s.location)
        items.append({
            "id": s.id,
            "owner_id": s.owner_id,
            "name": s.name,
            "description": s.description,
            "address": s.address,
            "phone": s.phone,
            "opening_hours": s.opening_hours,
            "is_active": s.is_active,
            "is_orderable": s.is_orderable,
            "verification_status": s.verification_status,
            "source": s.source,
            "source_id": s.source_id,
            "source_attribution": s.source_attribution,
            "original_url": s.original_url,
            "import_batch_id": s.import_batch_id,
            "imported_at": s.imported_at,
            "last_seen_at": s.last_seen_at,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
            "location": {"latitude": point.y, "longitude": point.x},
            "distance_meters": None,
            "is_delivery_eligible": None,
            "delivery_radius_meters": DEFAULT_DELIVERY_RADIUS_METERS
        })
        
    return items, total

async def check_shop_delivery_eligibility(
    db: AsyncSession,
    shop_id: str | uuid.UUID,
    latitude: float,
    longitude: float
) -> Dict[str, Any]:
    DEFAULT_DELIVERY_RADIUS_METERS = 5000
    shop = await get_shop_by_id_or_identifier(db, str(shop_id))

    is_dict = isinstance(shop, dict)
    shop_obj_id = shop["id"] if is_dict else shop.id
    shop_name = shop["name"] if is_dict else shop.name
    is_active = shop["is_active"] if is_dict else shop.is_active
    is_orderable = shop["is_orderable"] if is_dict else shop.is_orderable
    verification_status = shop["verification_status"] if is_dict else shop.verification_status

    if is_dict:
        shop_lat = shop["location"]["latitude"]
        shop_lon = shop["location"]["longitude"]
        from app.services.geoapify import haversine_distance_meters
        dist_float = haversine_distance_meters(latitude, longitude, shop_lat, shop_lon)
        dist_km = round(dist_float / 1000.0, 1)
    else:
        user_point = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
        user_geog = cast(user_point, Geography())
        shop_geog = cast(Shop.location, Geography())

        dist_query = select(func.ST_Distance(shop_geog, user_geog)).where(Shop.id == shop.id)
        dist_val = (await db.execute(dist_query)).scalar_one()
        dist_float = round(float(dist_val), 1)
        dist_km = round(dist_float / 1000.0, 1)

    if not is_active:
        is_eligible = False
        message = f"Shop '{shop_name}' is currently closed or inactive. Delivery is unavailable."
    elif not is_orderable or verification_status != ShopVerificationStatus.verified:
        is_eligible = False
        message = f"Shop '{shop_name}' is a directory listing and does not currently accept online delivery orders."
    elif dist_float <= float(DEFAULT_DELIVERY_RADIUS_METERS):
        is_eligible = True
        message = f"Shop is {dist_km} km away. Delivery is available to your location."
    else:
        is_eligible = False
        message = f"Shop is {dist_km} km away, which exceeds the {int(DEFAULT_DELIVERY_RADIUS_METERS / 1000)} km maximum delivery radius. Store pickup only."

    return {
        "shop_id": shop_obj_id,
        "shop_name": shop_name,
        "customer_location": {"latitude": latitude, "longitude": longitude},
        "distance_meters": dist_float,
        "is_delivery_eligible": is_eligible,
        "delivery_radius_meters": DEFAULT_DELIVERY_RADIUS_METERS,
        "message": message
    }
