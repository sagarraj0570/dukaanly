import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, ConfigDict, model_validator

class LocationInput(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)

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
    location: LocationInput | None = None
    is_active: bool | None = None

class ShopResponse(ShopBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    is_active: bool
    location: LocationInput
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
                "owner_id": data.owner_id,
                "name": data.name,
                "description": data.description,
                "address": data.address,
                "is_active": data.is_active,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
                "location": {"latitude": point.y, "longitude": point.x}
            }
        return data

class ShopListResponse(BaseModel):
    items: list[ShopResponse]
    total: int
    page: int
    size: int
