import asyncio
import hashlib
import json
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class OSRMError(Exception):
    """Base exception for all OSRM routing errors."""
    pass


class OSRMInvalidCoordinatesError(OSRMError):
    """Raised when coordinates are outside valid geographical bounds or malformed."""
    pass


class OSRMNoRouteError(OSRMError):
    """Raised when OSRM indicates NoRoute between the requested points."""
    pass


class OSRMTimeoutError(OSRMError):
    """Raised when upstream OSRM request times out."""
    pass


class OSRMProviderError(OSRMError):
    """Raised when upstream OSRM returns non-200 HTTP code, malformed JSON, or connection fails."""
    pass


def validate_coordinates(lat: float, lon: float, name: str = "point") -> None:
    """Validate that coordinates fall within standard WGS84 bounds."""
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        raise OSRMInvalidCoordinatesError(f"Coordinates must be numeric for {name}: lat={lat}, lon={lon}")
    if math.isnan(lat) or math.isnan(lon) or math.isinf(lat) or math.isinf(lon):
        raise OSRMInvalidCoordinatesError(f"Coordinates cannot be NaN or Inf for {name}: lat={lat}, lon={lon}")
    if not (-90.0 <= lat <= 90.0):
        raise OSRMInvalidCoordinatesError(f"Latitude must be between -90 and 90 for {name}: got {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise OSRMInvalidCoordinatesError(f"Longitude must be between -180 and 180 for {name}: got {lon}")


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points on the earth in meters."""
    r = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def estimate_fallback_duration(distance_meters: float) -> float:
    """Estimate duration in seconds based on average urban driving speed (22 km/h)."""
    if distance_meters <= 0:
        return 0.0
    average_urban_speed_mps = (22.0 * 1000.0) / 3600.0
    return round(distance_meters / average_urban_speed_mps, 1)


def generate_osrm_cache_key(lat1: float, lon1: float, lat2: float, lon2: float, profile: str = "driving") -> str:
    """Generate a cache key rounding coordinates to ~11m (4 decimals) for cache hits."""
    r_lat1 = round(lat1, 4)
    r_lon1 = round(lon1, 4)
    r_lat2 = round(lat2, 4)
    r_lon2 = round(lon2, 4)
    key_str = f"{profile}:{r_lat1},{r_lon1};{r_lat2},{r_lon2}"
    h = hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:16]
    return f"osrm:route:{h}"


# Global HTTP client singleton and bounded concurrency semaphore
_osrm_http_client: Optional[httpx.AsyncClient] = None
_osrm_http_client_loop: Optional[asyncio.AbstractEventLoop] = None

_osrm_semaphore: Optional[asyncio.Semaphore] = None
_osrm_semaphore_loop: Optional[asyncio.AbstractEventLoop] = None


async def get_osrm_http_client() -> httpx.AsyncClient:
    """
    Return a shared HTTPX client with connection pooling and keep-alive for OSRM queries.
    Safely re-initializes client if running in a new asyncio event loop (e.g. across tests).
    """
    global _osrm_http_client, _osrm_http_client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _osrm_http_client is not None and current_loop is not None and _osrm_http_client_loop != current_loop:
        _osrm_http_client = None
        _osrm_http_client_loop = None

    if _osrm_http_client is None or _osrm_http_client.is_closed:
        max_req = getattr(settings, "OSRM_MAX_CONCURRENT_REQUESTS", 10)
        limits = httpx.Limits(
            max_keepalive_connections=max_req,
            max_connections=max_req * 2,
            keepalive_expiry=30.0,
        )
        timeout_val = getattr(settings, "OSRM_TIMEOUT_SECONDS", 4.0)
        _osrm_http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=2.0,
                read=timeout_val,
                write=timeout_val,
                pool=2.0,
            ),
            limits=limits,
        )
        _osrm_http_client_loop = current_loop
    return _osrm_http_client


async def close_osrm_http_client() -> None:
    """Close the shared OSRM HTTP client and reset singleton."""
    global _osrm_http_client, _osrm_http_client_loop
    client = _osrm_http_client
    _osrm_http_client = None
    _osrm_http_client_loop = None
    if client is not None and not client.is_closed:
        try:
            await client.aclose()
        except Exception:
            pass


def get_osrm_semaphore() -> asyncio.Semaphore:
    """
    Return an asyncio.Semaphore enforcing bounded concurrency on OSRM requests.
    Safely re-initializes semaphore if running in a new asyncio event loop.
    """
    global _osrm_semaphore, _osrm_semaphore_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _osrm_semaphore is not None and current_loop is not None and _osrm_semaphore_loop != current_loop:
        _osrm_semaphore = None
        _osrm_semaphore_loop = None

    if _osrm_semaphore is None:
        max_concurrent = getattr(settings, "OSRM_MAX_CONCURRENT_REQUESTS", 10)
        _osrm_semaphore = asyncio.Semaphore(max_concurrent)
        _osrm_semaphore_loop = current_loop
    return _osrm_semaphore


class OSRMRoutingService:
    """
    Production-grade client for the Open Source Routing Machine (OSRM) API.
    Features:
    - Route service with GeoJSON geometry and strict coordinate validation.
    - Table service for fast multi-candidate matrix routing.
    - Redis caching with configurable TTL (default 300s).
    - Shared connection pooling with keep-alive and bounded concurrency.
    - Graceful Redis and OSRM failure handling.
    - Explicit typed domain exceptions (never invent fake routes when OSRM fails).
    """

    @property
    def base_url(self) -> str:
        return settings.OSRM_BASE_URL.rstrip("/")

    @property
    def cache_ttl(self) -> int:
        return settings.OSRM_CACHE_TTL_SECONDS

    @property
    def timeout(self) -> float:
        return getattr(settings, "OSRM_TIMEOUT_SECONDS", 4.0)

    async def _get_redis_client(self):
        """Retrieve shared async Redis client from app.core.redis."""
        try:
            from app.core.redis import get_redis_client
            return await get_redis_client()
        except Exception as e:
            logger.warning(f"OSRM Redis connection failed: {e}")
            return None

    async def get_two_point_route(
        self,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        profile: str = "driving",
        from_name: str = "Origin",
        to_name: str = "Destination",
    ) -> Dict[str, Any]:
        """
        Calculates a road route between two points using OSRM Route API.
        Validates coordinates, checks Redis cache, queries OSRM, and caches response.
        Raises OSRMError on failure (never fabricates artificial route on error).
        """
        validate_coordinates(start_lat, start_lon, name=from_name)
        validate_coordinates(end_lat, end_lon, name=to_name)

        # 1. Check Redis Cache
        cache_key = generate_osrm_cache_key(start_lat, start_lon, end_lat, end_lon, profile)
        redis_client = await self._get_redis_client()

        if redis_client:
            try:
                cached_data = await redis_client.get(cache_key)
                if cached_data:
                    parsed = json.loads(cached_data)
                    parsed["cached"] = True
                    parsed["from_name"] = from_name
                    parsed["to_name"] = to_name
                    return parsed
            except Exception as e:
                logger.warning(f"Error reading OSRM route cache: {e}")

        # 2. Call OSRM Upstream API with connection pooling & bounded concurrency
        # OSRM expects coordinates in {longitude},{latitude} order!
        coords_param = f"{start_lon},{start_lat};{end_lon},{end_lat}"
        url = f"{self.base_url}/route/v1/{profile}/{coords_param}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "false",
        }

        try:
            semaphore = get_osrm_semaphore()
            async with semaphore:
                client = await get_osrm_http_client()
                response = await client.get(url, params=params)

            if response.status_code == 200:
                try:
                    data = response.json()
                except Exception as e:
                    raise OSRMProviderError(f"OSRM returned malformed JSON: {e}") from e

                if data.get("code") == "Ok":
                    routes = data.get("routes")
                    if not routes:
                        raise OSRMNoRouteError("OSRM returned Ok but routes list was empty")

                    route = routes[0]
                    distance_m = float(route.get("distance", 0.0))
                    duration_s = float(route.get("duration", 0.0))

                    # Convert GeoJSON [[lon, lat], ...] to Leaflet [[lat, lon], ...]
                    geojson_coords = route.get("geometry", {}).get("coordinates", [])
                    leaflet_polyline = [[pt[1], pt[0]] for pt in geojson_coords]

                    result = {
                        "from_name": from_name,
                        "to_name": to_name,
                        "from_latitude": start_lat,
                        "from_longitude": start_lon,
                        "to_latitude": end_lat,
                        "to_longitude": end_lon,
                        "distance_meters": round(distance_m, 1),
                        "duration_seconds": round(duration_s, 1),
                        "duration_minutes": round(duration_s / 60.0, 1),
                        "geometry": leaflet_polyline,
                        "is_fallback": False,
                        "cached": False,
                    }

                    # Cache successful route in Redis
                    if redis_client:
                        try:
                            await redis_client.set(
                                cache_key,
                                json.dumps(result),
                                ex=self.cache_ttl,
                            )
                        except Exception as e:
                            logger.warning(f"Error saving OSRM route to cache: {e}")

                    return result
                elif data.get("code") == "NoRoute":
                    raise OSRMNoRouteError("No route found between the specified coordinates")
                else:
                    raise OSRMProviderError(f"OSRM returned unexpected status code: {data.get('code')}")

            elif response.status_code == 400:
                try:
                    err_json = response.json()
                    if err_json.get("code") == "NoRoute":
                        raise OSRMNoRouteError("No route found between the specified coordinates")
                except (ValueError, KeyError, json.JSONDecodeError):
                    pass
                raise OSRMProviderError(f"OSRM request rejected: HTTP 400 {response.text[:150]}")
            else:
                raise OSRMProviderError(f"OSRM returned HTTP {response.status_code}: {response.text[:150]}")

        except httpx.TimeoutException as e:
            logger.warning(f"OSRM request timed out after {self.timeout}s: {e}")
            raise OSRMTimeoutError(f"OSRM upstream request timed out after {self.timeout}s") from e
        except httpx.RequestError as e:
            logger.warning(f"OSRM network error: {e}")
            raise OSRMProviderError(f"OSRM connection failed: {e}") from e
        except OSRMError:
            raise
        except Exception as e:
            logger.warning(f"OSRM unexpected error: {e}")
            raise OSRMProviderError(f"OSRM unexpected error: {e}") from e

    async def get_table_matrix(
        self,
        sources: List[Tuple[float, float]],
        destinations: List[Tuple[float, float]],
        profile: str = "driving",
    ) -> Dict[str, Any]:
        """
        Query OSRM Table API for duration and distance matrix between sources and destinations.
        sources: List of (lat, lon)
        destinations: List of (lat, lon)
        Returns:
            {
                "durations": [[float, ...], ...], # durations[source_idx][dest_idx] in seconds
                "distances": [[float, ...], ...], # distances[source_idx][dest_idx] in meters
            }
        """
        if not sources or not destinations:
            return {"durations": [], "distances": []}

        for i, (lat, lon) in enumerate(sources):
            validate_coordinates(lat, lon, name=f"source_{i}")
        for j, (lat, lon) in enumerate(destinations):
            validate_coordinates(lat, lon, name=f"destination_{j}")

        all_points = list(sources) + list(destinations)
        coords_str = ";".join(f"{lon},{lat}" for lat, lon in all_points)
        source_indices = ";".join(str(i) for i in range(len(sources)))
        dest_indices = ";".join(str(len(sources) + j) for j in range(len(destinations)))

        url = f"{self.base_url}/table/v1/{profile}/{coords_str}"
        params = {
            "sources": source_indices,
            "destinations": dest_indices,
            "annotations": "duration,distance",
        }

        try:
            semaphore = get_osrm_semaphore()
            async with semaphore:
                client = await get_osrm_http_client()
                response = await client.get(url, params=params)

            if response.status_code == 200:
                try:
                    data = response.json()
                except Exception as e:
                    raise OSRMProviderError(f"OSRM Table returned malformed JSON: {e}") from e

                if data.get("code") == "Ok":
                    return {
                        "durations": data.get("durations", []),
                        "distances": data.get("distances", []),
                    }
                elif data.get("code") == "NoRoute":
                    raise OSRMNoRouteError("No table route found for candidates")
                else:
                    raise OSRMProviderError(f"OSRM Table returned error code: {data.get('code')}")
            else:
                raise OSRMProviderError(f"OSRM Table HTTP {response.status_code}")

        except httpx.TimeoutException as e:
            logger.warning(f"OSRM Table request timed out: {e}")
            raise OSRMTimeoutError("OSRM Table request timed out") from e
        except httpx.RequestError as e:
            logger.warning(f"OSRM Table connection error: {e}")
            raise OSRMProviderError(f"OSRM Table connection failed: {e}") from e
        except OSRMError:
            raise
        except Exception as e:
            logger.warning(f"OSRM Table unexpected error: {e}")
            raise OSRMProviderError(f"OSRM Table unexpected error: {e}") from e

    async def get_multi_leg_delivery_route(
        self,
        rider_loc: Optional[Tuple[float, float]],
        shop_loc: Tuple[float, float],
        customer_loc: Tuple[float, float],
        delivery_status: str,
    ) -> Dict[str, Any]:
        """
        Builds the complete multi-leg delivery route.
        - Leg 1 (Pickup): Rider -> Shop (if rider location available)
        - Leg 2 (Dropoff): Shop -> Customer
        Raises OSRMError on failure.
        """
        shop_lat, shop_lon = shop_loc
        cust_lat, cust_lon = customer_loc

        # Dropoff Leg (Shop -> Customer)
        dropoff_task = self.get_two_point_route(
            start_lat=shop_lat,
            start_lon=shop_lon,
            end_lat=cust_lat,
            end_lon=cust_lon,
            from_name="Shop",
            to_name="Customer",
        )

        pickup_task = None
        if rider_loc is not None:
            rider_lat, rider_lon = rider_loc
            pickup_task = self.get_two_point_route(
                start_lat=rider_lat,
                start_lon=rider_lon,
                end_lat=shop_lat,
                end_lon=shop_lon,
                from_name="Rider",
                to_name="Shop",
            )

        if pickup_task:
            leg_pickup, leg_dropoff = await asyncio.gather(pickup_task, dropoff_task)
            legs = [leg_pickup, leg_dropoff]
        else:
            leg_dropoff = await dropoff_task
            legs = [leg_dropoff]

        total_distance = sum(leg["distance_meters"] for leg in legs)
        total_duration = sum(leg["duration_seconds"] for leg in legs)
        all_cached = all(leg.get("cached", False) for leg in legs)

        # Combined polyline: chain leg geometries
        combined_geometry = []
        for leg in legs:
            geom = leg.get("geometry", [])
            if not combined_geometry:
                combined_geometry.extend(geom)
            else:
                combined_geometry.extend(geom[1:] if len(geom) > 1 else geom)

        # Determine active leg index
        if len(legs) == 2:
            if delivery_status in ["assigned"]:
                active_leg_index = 0
            else:
                active_leg_index = 1
        else:
            active_leg_index = 0

        return {
            "legs": legs,
            "total_distance_meters": round(total_distance, 1),
            "total_duration_seconds": round(total_duration, 1),
            "total_duration_minutes": round(total_duration / 60.0, 1),
            "combined_geometry": combined_geometry,
            "active_leg_index": active_leg_index,
            "is_fallback": False,
            "cached": all_cached,
            "attribution": "Route data © OpenStreetMap contributors, powered by OSRM",
        }

    async def check_routing_health(self) -> Dict[str, Any]:
        """
        Probe OSRM routing engine availability using a quick nearest-point query in Patna.
        Never throws unhandled exceptions; returns structured health status.
        """
        # Central Patna coordinate test point (Boring Road / Bailey Road junction: 85.1158, 25.6144)
        test_lon, test_lat = 85.1158, 25.6144
        url = f"{self.base_url}/nearest/v1/driving/{test_lon},{test_lat}"

        try:
            semaphore = get_osrm_semaphore()
            async with semaphore:
                client = await get_osrm_http_client()
                response = await client.get(url)

            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("code") == "Ok":
                        return {
                            "status": "healthy",
                            "provider": settings.ROUTING_PROVIDER,
                            "base_url": self.base_url,
                            "details": "OSRM routing service operational",
                        }
                    else:
                        return {
                            "status": "degraded",
                            "provider": settings.ROUTING_PROVIDER,
                            "base_url": self.base_url,
                            "details": f"OSRM returned unexpected code: {data.get('code')}",
                        }
                except Exception as e:
                    return {
                        "status": "degraded",
                        "provider": settings.ROUTING_PROVIDER,
                        "base_url": self.base_url,
                        "details": f"OSRM returned malformed JSON: {e}",
                    }
            else:
                return {
                    "status": "unreachable",
                    "provider": settings.ROUTING_PROVIDER,
                    "base_url": self.base_url,
                    "details": f"OSRM returned HTTP {response.status_code}",
                }
        except httpx.TimeoutException:
            return {
                "status": "unreachable",
                "provider": settings.ROUTING_PROVIDER,
                "base_url": self.base_url,
                "details": f"OSRM health probe timed out after {self.timeout}s",
            }
        except Exception as e:
            return {
                "status": "unreachable",
                "provider": settings.ROUTING_PROVIDER,
                "base_url": self.base_url,
                "details": f"OSRM health probe failed: {e.__class__.__name__}",
            }


# Global singleton instance
osrm_service = OSRMRoutingService()
