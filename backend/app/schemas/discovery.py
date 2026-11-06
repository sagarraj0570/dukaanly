import uuid
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

class NearbyStoreListing(BaseModel):
    """
    Normalized representation of a real-world external business discovered via Geoapify Places API.
    Strictly a directory-only listing: non-orderable and not registered as a Dukaanly merchant.
    """
    source: str = "geoapify"
    source_id: Optional[str] = None
    name: str = Field(..., description="Business name")
    category: str = Field(..., description="Normalized retail category")
    address: str = Field(..., description="Formatted street/locality address")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    distance_meters: Optional[float] = Field(None, description="Distance from requested coordinates in meters")
    phone: Optional[str] = None
    website: Optional[str] = None
    opening_hours: Optional[str] = None
    
    # Invariant flags
    is_directory_listing: bool = True
    is_dukaanly_merchant: bool = False
    is_orderable: bool = False
    is_delivery_eligible: bool = False
    attribution: str = "Powered by Geoapify | © OpenStreetMap contributors"

    model_config = ConfigDict(from_attributes=True)


class NearbyDiscoveryResponse(BaseModel):
    """
    Envelope response for nearby external store discovery.
    """
    items: List[NearbyStoreListing]
    total: int
    latitude: float
    longitude: float
    radius_meters: int
    category: Optional[str] = None
    cached: bool = False
    attribution: str = "Powered by Geoapify | © OpenStreetMap contributors"
