from typing import Optional
from fastapi import APIRouter, Query, status

from app.schemas.discovery import NearbyDiscoveryResponse
from app.services.geoapify import GeoapifyPlacesService

router = APIRouter()

@router.get(
    "/nearby",
    response_model=NearbyDiscoveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Discover nearby external retail stores via Geoapify Places API",
    description=(
        "Returns transient, read-only directory listings of real-world stores within the specified radius. "
        "These listings are not orderable Dukaanly merchants and cannot be added to a cart."
    ),
)
async def discover_nearby_stores(
    lat: float = Query(
        ...,
        ge=-90.0,
        le=90.0,
        description="Customer latitude (-90.0 to 90.0)",
        examples=[25.6144],
    ),
    lon: float = Query(
        ...,
        ge=-180.0,
        le=180.0,
        description="Customer longitude (-180.0 to 180.0)",
        examples=[85.1158],
    ),
    radius: int = Query(
        3000,
        ge=100,
        le=10000,
        description="Search radius in meters (100m to 10,000m)",
        examples=[3000],
    ),
    category: Optional[str] = Query(
        None,
        description="Retail category filter (e.g., grocery, supermarket, chemist, bakery)",
        examples=["grocery"],
    ),
    limit: int = Query(
        20,
        ge=1,
        le=25,
        description="Maximum results to return (1 to 25)",
        examples=[20],
    ),
):
    service = GeoapifyPlacesService()
    return await service.fetch_nearby_stores(
        lat=lat,
        lon=lon,
        radius=radius,
        category=category,
        limit=limit,
    )
