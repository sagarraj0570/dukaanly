"""
OpenStreetMap Overpass API Provider Adapter.
Complies with OpenStreetMap ODbL attribution and Acceptable Use Policy.
Does not use Nominatim for POI extraction.
"""

import logging
from typing import List, Dict, Any, Optional
import httpx

from app.services.importer.base import BaseListingProvider, AreaConfig, NormalizedListing

logger = logging.getLogger(__name__)

SUPPORTED_OSM_CATEGORIES = {
    "grocery": "grocery",
    "supermarket": "supermarket",
    "convenience": "convenience",
    "chemist": "chemist",
    "bakery": "bakery",
    "dairy": "dairy",
    "general": "grocery",
}

class OSMOverpassProvider(BaseListingProvider):
    """
    OpenStreetMap Overpass API adapter.
    Queries bounded bounding boxes for approved retail categories.
    """

    OVERPASS_ENDPOINTS = [
        "https://overpass-api.de/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]

    def __init__(self, timeout_seconds: int = 10, max_retries: int = 2):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    @property
    def provider_name(self) -> str:
        return "osm"

    @property
    def attribution(self) -> str:
        return "© OpenStreetMap contributors, ODbL"

    def validate_and_normalize(
        self,
        raw_item: Dict[str, Any],
        area: AreaConfig
    ) -> Optional[NormalizedListing]:
        tags = raw_item.get("tags", {})
        name = tags.get("name", "").strip()
        if not name:
            return None

        lat = raw_item.get("lat")
        lon = raw_item.get("lon")
        if lat is None or lon is None:
            return None

        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            return None

        if not area.contains(lat, lon):
            return None

        osm_category = tags.get("shop", "grocery")
        category = SUPPORTED_OSM_CATEGORIES.get(osm_category, "grocery")

        node_id = raw_item.get("id")
        source_id = f"osm:node:{node_id}" if node_id else None
        if not source_id:
            return None

        # Build clean address
        street = tags.get("addr:street")
        locality = tags.get("addr:suburb") or tags.get("addr:neighbourhood") or area.city
        postcode = tags.get("addr:postcode")
        address_parts = [p for p in [street, locality, area.city, area.state, postcode] if p]
        address = ", ".join(address_parts) if address_parts else f"{locality}, {area.city}, {area.state}"

        phone = tags.get("phone") or tags.get("contact:phone")
        opening_hours = tags.get("opening_hours")
        original_url = f"https://www.openstreetmap.org/node/{node_id}" if node_id else None

        return NormalizedListing(
            name=name,
            category=category,
            address=address,
            latitude=lat,
            longitude=lon,
            source=self.provider_name,
            source_id=source_id,
            source_attribution=self.attribution,
            phone=phone,
            opening_hours=opening_hours,
            original_url=original_url,
            raw_data=raw_item,
        )

    async def fetch_candidate_listings(
        self,
        area: AreaConfig,
        categories: List[str],
        max_records: int = 100
    ) -> List[NormalizedListing]:
        """Fetch candidate retail nodes using Overpass QL within the target bounding box."""
        # Build category filter
        category_pattern = "|".join([cat for cat in categories if cat in SUPPORTED_OSM_CATEGORIES] or list(SUPPORTED_OSM_CATEGORIES.keys()))

        query = f"""
        [out:json][timeout:{self.timeout_seconds}];
        (
          node["shop"~"{category_pattern}"]({area.min_lat},{area.min_lon},{area.max_lat},{area.max_lon});
        );
        out body {max_records};
        """

        for endpoint in self.OVERPASS_ENDPOINTS:
            for attempt in range(self.max_retries):
                try:
                    headers = {
                        "User-Agent": "Dukaanly-MerchantDiscovery/1.0 (contact: admin@dukaanly.com)",
                        "Accept": "application/json",
                    }
                    async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                        response = await client.post(endpoint, data={"data": query}, headers=headers)
                        if response.status_code == 200:
                            data = response.json()
                            elements = data.get("elements", [])
                            results: List[NormalizedListing] = []
                            for el in elements:
                                normalized = self.validate_and_normalize(el, area)
                                if normalized:
                                    results.append(normalized)
                                    if len(results) >= max_records:
                                        break
                            logger.info(f"OSM Overpass fetched {len(results)} valid candidate listings from {endpoint}")
                            return results
                        elif response.status_code == 429:
                            logger.warning(f"Overpass API rate limited (429) on attempt {attempt + 1}")
                except Exception as e:
                    logger.warning(f"Failed query to Overpass endpoint {endpoint} (attempt {attempt + 1}): {e}")

        logger.error("All Overpass API endpoints failed or timed out.")
        return []
