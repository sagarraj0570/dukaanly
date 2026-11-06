import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, ConfigDict, model_validator

class LocationInput(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)

from app.models.shop import ShopVerificationStatus

class ShopBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    address: str

class ShopCreate(ShopBase):
    location: LocationInput

class ShopUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    description: str | None = None
    address: str | None = None
    phone: str | None = None
    opening_hours: str | None = None
    location: LocationInput | None = None
    is_active: bool | None = None

class ShopResponse(ShopBase):
    id: uuid.UUID
    owner_id: uuid.UUID | None = None
    is_active: bool
    is_orderable: bool = False
    verification_status: ShopVerificationStatus = ShopVerificationStatus.discovered
    source: str | None = None
    source_id: str | None = None
    source_attribution: str | None = None
    original_url: str | None = None
    import_batch_id: uuid.UUID | None = None
    imported_at: datetime | None = None
    last_seen_at: datetime | None = None
    phone: str | None = None
    opening_hours: str | None = None
    location: LocationInput
    distance_meters: float | None = None
    is_delivery_eligible: bool | None = None
    delivery_radius_meters: int = 5000
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='before')
    @classmethod
    def convert_location(cls, data: Any) -> Any:
        # data might be a dictionary or an ORM model
        if isinstance(data, dict):
            return data
            
        from geoalchemy2.elements import WKBElement
        from geoalchemy2.shape import to_shape

        if hasattr(data, 'location') and isinstance(data.location, WKBElement):
            point = to_shape(data.location)
            # Create a dict representation to avoid mutating the ORM instance
            return {
                "id": data.id,
                "owner_id": getattr(data, 'owner_id', None),
                "name": data.name,
                "description": data.description,
                "address": data.address,
                "phone": getattr(data, 'phone', None),
                "opening_hours": getattr(data, 'opening_hours', None),
                "is_active": data.is_active,
                "is_orderable": getattr(data, 'is_orderable', False),
                "verification_status": getattr(data, 'verification_status', ShopVerificationStatus.discovered),
                "source": getattr(data, 'source', None),
                "source_id": getattr(data, 'source_id', None),
                "source_attribution": getattr(data, 'source_attribution', None),
                "original_url": getattr(data, 'original_url', None),
                "imported_at": getattr(data, 'imported_at', None),
                "last_seen_at": getattr(data, 'last_seen_at', None),
                "created_at": data.created_at,
                "updated_at": data.updated_at,
                "location": {"latitude": point.y, "longitude": point.x},
                "distance_meters": getattr(data, 'distance_meters', None),
                "is_delivery_eligible": getattr(data, 'is_delivery_eligible', None),
                "delivery_radius_meters": getattr(data, 'delivery_radius_meters', 5000)
            }
        return data

class ShopListResponse(BaseModel):
    items: list[ShopResponse]
    total: int
    page: int
    size: int
    user_latitude: float | None = None
    user_longitude: float | None = None
    radius_meters: int | None = None

class DeliveryEligibilityResponse(BaseModel):
    shop_id: uuid.UUID
    shop_name: str
    customer_location: LocationInput
    distance_meters: float
    is_delivery_eligible: bool
    delivery_radius_meters: int
    message: str
