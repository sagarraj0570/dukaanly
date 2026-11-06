"""
Geoapify Places API Service Integration.
Provides live nearby external store discovery with coordinate grid caching,
transient retry handling, sanitized logging, and strict read-only directory boundaries.
"""

import asyncio
import json
import logging
import math
import re
import time
import uuid
from typing import List, Dict, Any, Optional, Tuple
from collections import OrderedDict
import httpx
from fastapi import HTTPException, status
import redis.asyncio as aioredis

from app.core.config import settings
from app.schemas.discovery import NearbyStoreListing, NearbyDiscoveryResponse

logger = logging.getLogger(__name__)

# Dukaanly retail categories mapped to official Geoapify Places category hierarchy
CATEGORY_MAPPING: Dict[str, str] = {
    "grocery": "commercial.supermarket,commercial.convenience,commercial.food_and_drink",
    "supermarket": "commercial.supermarket",
    "convenience": "commercial.convenience",
    "chemist": "healthcare.pharmacy,commercial.chemist",
    "pharmacy": "healthcare.pharmacy,commercial.chemist",
    "bakery": "commercial.food_and_drink.bakery",
    "dairy": "commercial.food_and_drink",
    "produce": "commercial.food_and_drink",
    "fruits": "commercial.food_and_drink",
    "general": "commercial.supermarket,commercial.convenience,commercial.food_and_drink",
}

DEFAULT_CATEGORIES = (
    "commercial.supermarket,commercial.convenience,commercial.food_and_drink,healthcare.pharmacy,commercial.food_and_drink.bakery"
)

# Reverse classification mapping for Geoapify category tags to Dukaanly category names
def classify_geoapify_category(categories: List[str], name: Optional[str] = None) -> str:
    cat_set = {c.lower() for c in categories}
    name_lower = (name or "").lower()

    # 1. Pharmacy / Chemist
    if (
        any("pharmacy" in c or "chemist" in c for c in cat_set)
        or any(k in name_lower for k in ["pharmacy", "chemist", "medical", "medicos", "druggist", "apollo", "medplus", "dawa"])
    ):
        return "chemist"

    # 2. Fashion & Apparel (e.g. Zudio, Trends, Pantaloons, garments, clothing)
    if (
        any("clothing" in c or "apparel" in c or "fashion" in c or "shoes" in c for c in cat_set)
        or any(k in name_lower for k in [
            "zudio", "trends", "max fashion", "pantaloons", "fabindia", "raymond", "mufti", "zara", "h&m",
            "shoppers stop", "westside", "peter england", "manyavar", "allen solly", "louis philippe",
            "v-mart", "vmart", "vishal mega mart",
            "clothing", "apparel", "garment", "garments", "fashion", "boutique", "textile", "dresses",
            "menswear", "womenswear", "kidswear", "footwear", "shoes", "sneakers"
        ])
    ):
        return "fashion"

    # 3. Health & Sports Nutrition (e.g. Active nutrition centtre, protein, fitness)
    if (
        any("fitness" in c or "nutrition" in c for c in cat_set)
        or any(k in name_lower for k in [
            "nutrition", "protein", "fitness", "supplement", "supplements", "nutra", "gym", "bodybuilding", "active nutrition", "whey", "creatine"
        ])
    ):
        return "nutrition"

    # 4. Home Living & Furniture (e.g. Home town, furniture, home decor)
    if (
        any("furniture" in c or "houseware" in c or "homeware" in c for c in cat_set)
        or any(k in name_lower for k in [
            "home town", "hometown", "furniture", "home decor", "furnishing", "furnishings", "interiors", "interior", "mattress", "sleepwell", "kurlon"
        ])
    ):
        return "home_living"

    # 5. Electronics & Mobiles
    if (
        any("electronic" in c for c in cat_set)
        or any(k in name_lower for k in [
            "electronics", "mobile", "mobiles", "computer", "laptop", "croma", "reliance digital", "vijay sales", "sangeetha", "poorvika", "gadget"
        ])
    ):
        return "electronics"

    # 6. Bakery & Confectionery
    if (
        any("bakery" in c for c in cat_set)
        or any(k in name_lower for k in [
            "bakery", "cake", "cakes", "pastry", "pastries", "sweets", "confectionery", "mithai", "harilal", "haldiram", "bikanervala", "monginis", "bake"
        ])
    ):
        return "bakery"

    # 7. Dairy & Milk Parlour
    if (
        any("dairy" in c or "milk" in c for c in cat_set)
        or any(k in name_lower for k in [
            "sudha", "amul", "mother dairy", "dairy", "milk parlour", "milk booth", "creamery"
        ])
    ):
        return "dairy"

    # 8. Fresh Produce
    if (
        any("produce" in c or "vegetable" in c or "fruit" in c for c in cat_set)
        or any(k in name_lower for k in ["sabzi", "mandi", "vegetable", "fruit", "fruits & veg"])
    ):
        return "produce"

    # 9. Supermarket / Mart
    if (
        any("supermarket" in c for c in cat_set)
        or any(k in name_lower for k in ["mart", "supermarket", "hypermarket", "bazaar", "departmental"])
    ):
        return "supermarket"

    # 10. Convenience Store
    if any("convenience" in c for c in cat_set):
        return "convenience"

    return "grocery"


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on Earth in meters."""
    R = 6371000.0  # Earth's radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 1)


# Bounded in-memory fallback cache (LRU + TTL)
class InMemoryDiscoveryCache:
    def __init__(self, max_size: int = 200, default_ttl: int = 300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, Tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        expires_at, value = self._cache[key]
        if time.time() > expires_at:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl or self.default_ttl
        if len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)
        self._cache[key] = (time.time() + ttl, value)

    def clear(self) -> None:
        self._cache.clear()


_memory_cache = InMemoryDiscoveryCache(max_size=200, default_ttl=300)


async def find_cached_discovery_place(identifier: str) -> Optional[Dict[str, Any]]:
    """
    Look up a discovered place by source_id, deterministic UUID, or name across active cache (memory + Redis).
    """
    ident_lower = identifier.lower().strip()
    now = time.time()
    for expires_at, value in _memory_cache._cache.values():
        if now <= expires_at and isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue
                src_id = str(item.get("source_id") or "").lower().strip()
                name = str(item.get("name") or "").lower().strip()
                det_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, item.get("source_id") or item.get("name") or "")).lower()
                if src_id == ident_lower or name == ident_lower or det_uuid == ident_lower:
                    return item

    # Check Redis cache
    try:
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        keys = await client.keys("dukaanly:geoapify:places:*")
        for k in keys[:30]:
            raw_val = await client.get(k)
            if raw_val:
                items = json.loads(raw_val)
                if isinstance(items, list):
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        src_id = str(item.get("source_id") or "").lower().strip()
                        name = str(item.get("name") or "").lower().strip()
                        det_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, item.get("source_id") or item.get("name") or "")).lower()
                        if src_id == ident_lower or name == ident_lower or det_uuid == ident_lower:
                            _memory_cache.set(k, items)
                            await client.aclose()
                            return item
        await client.aclose()
    except Exception as e:
        logger.debug(f"Redis lookup in find_cached_discovery_place skipped: {e}")

    return None


class GeoapifyPlacesService:
    """
    Client and Normalizer for Geoapify Places API v2.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        cache_ttl: Optional[int] = None,
    ):
        self.api_key = api_key if api_key is not None else settings.GEOAPIFY_API_KEY
        self.base_url = base_url or settings.GEOAPIFY_BASE_URL
        self.timeout = timeout or settings.GEOAPIFY_REQUEST_TIMEOUT_SECONDS
        self.cache_ttl = cache_ttl or settings.GEOAPIFY_CACHE_TTL_SECONDS

    def get_cache_key(
        self,
        lat: float,
        lon: float,
        radius: int,
        category: Optional[str],
        limit: int,
    ) -> str:
        """
        Normalize coordinates into a spatial grid (~110m resolution) to share cache hits.
        """
        grid_lat = round(lat, 3)
        grid_lon = round(lon, 3)
        cat_key = (category or "all").lower().strip()
        return f"dukaanly:geoapify:places:{grid_lat}:{grid_lon}:{radius}:{cat_key}:{limit}"

    async def _get_from_cache(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
        # 1. Try Redis cache if available
        try:
            client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            cached_data = await client.get(cache_key)
            await client.aclose()
            if cached_data:
                parsed = json.loads(cached_data)
                _memory_cache.set(cache_key, parsed)
                return parsed
        except Exception as e:
            logger.debug(f"Redis cache lookup skipped ({e}), checking in-memory cache")

        # 2. Try in-memory fallback cache
        return _memory_cache.get(cache_key)

    async def _save_to_cache(self, cache_key: str, data: List[Dict[str, Any]]) -> None:
        # Save in memory
        _memory_cache.set(cache_key, data, ttl=self.cache_ttl)

        # Save in Redis if available
        try:
            client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            await client.setex(cache_key, self.cache_ttl, json.dumps(data))
            await client.aclose()
        except Exception as e:
            logger.debug(f"Redis cache save skipped: {e}")

    async def _fetch_from_provider(self, query_params: Dict[str, Any]) -> httpx.Response:
        """Execute HTTP GET to Geoapify endpoint."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.get(self.base_url, params=query_params)

    def normalize_feature(
        self,
        feature: Dict[str, Any],
        user_lat: float,
        user_lon: float,
        radius: int,
    ) -> Optional[NearbyStoreListing]:
        """Defensively parse and normalize a raw Geoapify feature into NearbyStoreListing."""
        properties = feature.get("properties", {})
        if not properties or not isinstance(properties, dict):
            return None

        raw_name = properties.get("name", "").strip()
        if not raw_name:
            return None

        # Clean and format raw OSM store names (normalize casing and whitespace)
        clean_name = re.sub(r"\s+", " ", raw_name).strip()
        if clean_name.isupper() or clean_name.islower():
            clean_name = clean_name.title()

        name_lower = clean_name.lower()

        # Filter out irrelevant non-neighbourhood places (recharge kiosks, furniture, clothing stores)
        irrelevant_keywords = [
            "richarge", "recharge", "telecom", "mobile repair", "airtel", "jio point", "vi mini",
            "furniture", "furnishing", "home town", "hometown", "interiors", "mattress", "sleepwell",
            "zudio", "v-mart", "vmart", "trends", "clothing", "apparel", "garment", "footwear", "shoes"
        ]
        if any(kw in name_lower for kw in irrelevant_keywords):
            return None

        # Regional OSM typo and abbreviation cleanup
        name_fixes = {
            "homeo hal": "Homeo Hall & Healthcare",
            "homeo hall": "Homeo Hall & Healthcare",
            "jalal pur": "Jalalpur Kirana & General Store",
            "jalalpur": "Jalalpur Kirana & General Store",
        }
        for typo, fix in name_fixes.items():
            if name_lower == typo:
                clean_name = fix
                break

        name = clean_name

        # Coordinates
        lat = properties.get("lat")
        lon = properties.get("lon")
        if lat is None or lon is None:
            geom = feature.get("geometry", {})
            coords = geom.get("coordinates", [])
            if len(coords) >= 2:
                lon, lat = coords[0], coords[1]

        if lat is None or lon is None:
            return None

        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            return None

        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return None

        # Distance calculation
        prov_dist = properties.get("distance")
        if isinstance(prov_dist, (int, float)):
            dist_meters = round(float(prov_dist), 1)
        else:
            dist_meters = haversine_distance_meters(user_lat, user_lon, lat, lon)

        # Enforce radius with small 5% buffer for geodesic variances
        if dist_meters > radius * 1.05:
            return None

        # Address resolution
        address = (
            properties.get("formatted")
            or properties.get("address_line2")
            or properties.get("street")
        )
        if not address:
            suburb = properties.get("suburb") or properties.get("city") or ""
            address = f"{name}, {suburb}".strip(", ")

        # Category resolution
        feature_cats = properties.get("categories", [])
        category_name = classify_geoapify_category(feature_cats, name=name)

        # Optional contact and opening hours
        contact = properties.get("contact", {})
        if not isinstance(contact, dict):
            contact = {}

        phone = contact.get("phone") or properties.get("phone") or None
        website = contact.get("website") or properties.get("website") or None
        opening_hours = properties.get("opening_hours") or None

        # Stable source ID
        source_id = (
            properties.get("place_id")
            or feature.get("id")
            or f"geoapify:{lat:.5f}:{lon:.5f}"
        )

        return NearbyStoreListing(
            source="geoapify",
            source_id=str(source_id),
            name=name,
            category=category_name,
            address=str(address),
            latitude=lat,
            longitude=lon,
            distance_meters=dist_meters,
            phone=str(phone) if phone else None,
            website=str(website) if website else None,
            opening_hours=str(opening_hours) if opening_hours else None,
            is_directory_listing=True,
            is_dukaanly_merchant=False,
            is_orderable=False,
            is_delivery_eligible=False,
            attribution="Powered by Geoapify | © OpenStreetMap contributors",
        )

    async def fetch_nearby_stores(
        self,
        lat: float,
        lon: float,
        radius: int = 3000,
        category: Optional[str] = None,
        limit: int = 20,
    ) -> NearbyDiscoveryResponse:
        """
        Execute nearby store discovery via Geoapify Places API.
        Includes caching, parameter validation, transient retries, and sanitized logging.
        """
        # Validate coordinates and parameters
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Coordinates out of range. Latitude must be in [-90, 90] and longitude in [-180, 180].",
            )

        radius = max(100, min(radius, 10000))
        limit = max(1, min(limit, 25))

        # Check API key configuration
        if not self.api_key:
            logger.warning("GEOAPIFY_API_KEY is not configured in settings.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Geoapify Places API provider is not configured. Please contact the administrator.",
            )

        # Check Cache
        cache_key = self.get_cache_key(lat, lon, radius, category, limit)
        cached_items = await self._get_from_cache(cache_key)
        if cached_items is not None:
            listings = [NearbyStoreListing(**item) for item in cached_items]
            return NearbyDiscoveryResponse(
                items=listings,
                total=len(listings),
                latitude=lat,
                longitude=lon,
                radius_meters=radius,
                category=category,
                cached=True,
                attribution="Powered by Geoapify | © OpenStreetMap contributors",
            )

        # Resolve Geoapify category filter
        norm_cat = (category or "").lower().strip()
        geoapify_categories = CATEGORY_MAPPING.get(norm_cat, DEFAULT_CATEGORIES)

        # Geoapify parameters: filter=circle:lon,lat,radius; bias=proximity:lon,lat
        # Order: longitude first, then latitude!
        query_params: Dict[str, Any] = {
            "categories": geoapify_categories,
            "filter": f"circle:{lon},{lat},{radius}",
            "bias": f"proximity:{lon},{lat}",
            "limit": limit,
            "apiKey": self.api_key,
        }

        # Safe diagnostic logging (sanitized, NEVER log the key)
        logger.info(
            f"Querying Geoapify Places API: lat={lat:.4f}, lon={lon:.4f}, radius={radius}m, "
            f"cat={norm_cat or 'all'}, limit={limit}"
        )

        # Execute HTTP request with bounded transient retries
        features_data: List[Dict[str, Any]] = []
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                response = await self._fetch_from_provider(query_params)

                if response.status_code == 200:
                    try:
                        res_json = response.json()
                        features_data = res_json.get("features", [])
                    except Exception as json_err:
                        logger.error(f"Failed to parse Geoapify JSON response: {json_err}")
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="Invalid response payload from external places provider.",
                        )
                    break

                elif response.status_code in (401, 403):
                    logger.error(
                        f"Geoapify authentication/authorization error: HTTP {response.status_code}. "
                        "Check GEOAPIFY_API_KEY configuration."
                    )
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="External directory provider authentication failed. Check server configuration.",
                    )

                elif response.status_code == 429:
                    logger.warning("Geoapify Places API rate limit exceeded (HTTP 429).")
                    if attempt < max_retries:
                        retry_after = response.headers.get("Retry-After")
                        sleep_time = float(retry_after) if retry_after and retry_after.isdigit() else 1.0
                        await asyncio.sleep(sleep_time)
                        continue
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="External discovery provider rate limit exceeded. Please try again shortly.",
                    )

                elif response.status_code in (500, 502, 503, 504):
                    logger.warning(
                        f"Geoapify server error HTTP {response.status_code} (attempt {attempt + 1}/{max_retries + 1})"
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(0.5 * (2 ** attempt))
                        continue
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="External discovery service is currently experiencing upstream outages. Please retry later.",
                    )

                else:
                    logger.error(f"Geoapify returned unhandled HTTP {response.status_code}: {response.text}")
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"External directory provider returned status code {response.status_code}.",
                    )

            except httpx.RequestError as req_err:
                logger.warning(
                    f"Geoapify network error (attempt {attempt + 1}/{max_retries + 1}): {req_err}"
                )
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Connection to external places discovery provider timed out.",
                )

        # Normalize and deduplicate candidate features
        normalized_listings: List[NearbyStoreListing] = []
        seen_source_ids = set()
        seen_spatial = set()

        for feat in features_data:
            listing = self.normalize_feature(feat, user_lat=lat, user_lon=lon, radius=radius)
            if not listing:
                continue

            if listing.source_id and listing.source_id in seen_source_ids:
                continue

            spatial_key = (round(listing.latitude, 4), round(listing.longitude, 4), listing.name.lower().strip())
            if spatial_key in seen_spatial:
                continue

            seen_source_ids.add(listing.source_id)
            seen_spatial.add(spatial_key)
            normalized_listings.append(listing)

            if len(normalized_listings) >= limit:
                break

        # Sort by proximity
        normalized_listings.sort(key=lambda s: s.distance_meters if s.distance_meters is not None else 999999)

        # Cache successful validated results
        dict_items = [item.model_dump() for item in normalized_listings]
        await self._save_to_cache(cache_key, dict_items)

        return NearbyDiscoveryResponse(
            items=normalized_listings,
            total=len(normalized_listings),
            latitude=lat,
            longitude=lon,
            radius_meters=radius,
            category=category,
            cached=False,
            attribution="Powered by Geoapify | © OpenStreetMap contributors",
        )
