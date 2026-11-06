"""
OpenStreetMap (OSM) & Verified Regional Ingestion Engine for Patna Merchants.

Imports candidate retail business listings from OpenStreetMap (Overpass API / verified regional extract)
into Dukaanly as unverified, non-orderable directory listings (verification_status='discovered',
is_orderable=False, owner_id=None).
"""

import logging
from typing import List, Dict, Any, Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast
from geoalchemy2 import Geography

from app.models.shop import Shop, ShopVerificationStatus
from app.services.importer.curated_provider import PATNA_REGIONAL_EXTRACT

logger = logging.getLogger(__name__)

# Patna Metropolitan Envelope Validation Bounds
PATNA_BOUNDS = {
    "min_lat": 25.5500,
    "max_lat": 25.6500,
    "min_lon": 85.0500,
    "max_lon": 85.2500,
}

# Source Attribution
OSM_ATTRIBUTION = "© OpenStreetMap contributors, ODbL"

# Verified regional candidate listings (source-backed by Google Business / OSM / Geoapify)
CURATED_PATNA_LISTINGS: List[Dict[str, Any]] = PATNA_REGIONAL_EXTRACT


def validate_coordinates(lat: float, lon: float) -> bool:
    """Validate coordinates against Patna Metropolitan Envelope."""
    return (
        PATNA_BOUNDS["min_lat"] <= lat <= PATNA_BOUNDS["max_lat"]
        and PATNA_BOUNDS["min_lon"] <= lon <= PATNA_BOUNDS["max_lon"]
    )


async def fetch_overpass_patna(
    bbox: Optional[tuple[float, float, float, float]] = None,
    timeout_seconds: int = 8,
) -> List[Dict[str, Any]]:
    """
    Query Overpass API for retail shops in Patna bounding box.
    Gracefully catches connection timeouts or rate limits and falls back to curated listings.
    """
    if bbox is None:
        # Default Patna metropolitan BBox (south, west, north, east)
        bbox = (25.5500, 85.0500, 25.6500, 85.2500)

    south, west, north, east = bbox
    overpass_query = f"""
    [out:json][timeout:{timeout_seconds}];
    (
      node["shop"~"supermarket|convenience|grocery|chemist|bakery|dairy|general"]({south},{west},{north},{east});
    );
    out body;
    """

    overpass_endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ]

    for endpoint in overpass_endpoints:
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(endpoint, data={"data": overpass_query})
                if response.status_code == 200:
                    data = response.json()
                    elements = data.get("elements", [])
                    extracted = []
                    for el in elements:
                        tags = el.get("tags", {})
                        name = tags.get("name")
                        if not name:
                            continue
                        lat = el.get("lat")
                        lon = el.get("lon")
                        if not (lat and lon and validate_coordinates(lat, lon)):
                            continue

                        extracted.append({
                            "source_id": f"osm:node:{el.get('id')}",
                            "name": name,
                            "description": tags.get("description", f"Public OpenStreetMap listing for {name}."),
                            "address": tags.get("addr:street", f"Patna, Bihar"),
                            "category": tags.get("shop", "grocery"),
                            "latitude": float(lat),
                            "longitude": float(lon),
                            "phone": tags.get("phone") or tags.get("contact:phone"),
                            "opening_hours": tags.get("opening_hours"),
                            "source": "osm",
                            "source_attribution": OSM_ATTRIBUTION,
                        })
                    if extracted:
                        logger.info(f"Successfully fetched {len(extracted)} candidate POIs from Overpass API")
                        return extracted
        except Exception as e:
            logger.warning(f"Overpass endpoint {endpoint} failed or timed out: {e}")
            continue

    logger.info("Overpass API offline or empty. Returning curated Patna merchant dataset.")
    return CURATED_PATNA_LISTINGS


async def import_osm_listings(
    db: AsyncSession,
    listings: Optional[List[Dict[str, Any]]] = None,
    dedup_distance_meters: float = 25.0,
) -> Dict[str, Any]:
    """
    Ingest, normalize, deduplicate, and persist candidate Patna retail business listings.
    Sets verification_status='discovered', is_orderable=False, owner_id=None.
    """
    if listings is None:
        listings = CURATED_PATNA_LISTINGS

    stats = {
        "total_evaluated": len(listings),
        "imported": 0,
        "skipped_bounds": 0,
        "skipped_duplicate_source": 0,
        "skipped_spatial_dedup": 0,
    }

    seen_source_ids = set()

    for item in listings:
        lat = item.get("latitude")
        lon = item.get("longitude")
        source_id = item.get("source_id")
        name = item.get("name", "").strip()
        source = item.get("source", "osm")
        source_attribution = item.get("source_attribution", OSM_ATTRIBUTION)

        if not (lat and lon and validate_coordinates(lat, lon)):
            stats["skipped_bounds"] += 1
            continue

        # 1. Check composite unique key (source, source_id)
        if source_id:
            if source_id in seen_source_ids:
                stats["skipped_duplicate_source"] += 1
                continue
            existing_source = await db.execute(
                select(Shop).where(Shop.source == source, Shop.source_id == source_id)
            )
            if existing_source.scalar_one_or_none():
                stats["skipped_duplicate_source"] += 1
                continue
            seen_source_ids.add(source_id)

        # 2. Check spatial deduplication: is there an active non-archived shop within dedup_distance_meters?
        candidate_point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
        candidate_geog = cast(candidate_point, Geography())
        shop_geog = cast(Shop.location, Geography())

        spatial_check = await db.execute(
            select(Shop).where(
                Shop.is_active == True,
                Shop.verification_status != ShopVerificationStatus.archived,
                func.ST_DWithin(shop_geog, candidate_geog, dedup_distance_meters),
            )
        )
        near_shop = spatial_check.scalars().first()
        if near_shop:
            if near_shop.name.lower() == name.lower():
                stats["skipped_spatial_dedup"] += 1
                continue

        # 3. Insert new candidate listing
        point_wkt = f"SRID=4326;POINT({lon} {lat})"
        new_shop = Shop(
            owner_id=None,
            name=name,
            description=item.get("description", f"Local retail listing for {name}"),
            address=item.get("address", "Patna, Bihar"),
            phone=item.get("phone"),
            opening_hours=item.get("opening_hours"),
            location=point_wkt,
            is_active=True,
            is_orderable=False,
            verification_status=ShopVerificationStatus.discovered,
            source=source,
            source_id=source_id,
            source_attribution=source_attribution,
            original_url=item.get("original_url"),
        )
        db.add(new_shop)
        stats["imported"] += 1

    await db.commit()
    return stats
