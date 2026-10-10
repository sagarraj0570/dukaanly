import uuid
import typing
from pydantic import BaseModel, ConfigDict, Field, model_validator
from datetime import datetime

class RiderAvailabilityUpdate(BaseModel):
    is_available: bool

class RiderLocationUpdate(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)

class RiderProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    is_available: bool
    latitude: float | None = None
    longitude: float | None = None
    location_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='before')
    @classmethod
    def convert_location(cls, data: typing.Any) -> typing.Any:
        if isinstance(data, dict):
            return data
            
        from geoalchemy2.elements import WKBElement
        from geoalchemy2.shape import to_shape

        res = {
            "id": data.id,
            "user_id": data.user_id,
            "is_available": data.is_available,
            "created_at": data.created_at,
            "updated_at": data.updated_at,
            "location_updated_at": data.location_updated_at,
        }

        if hasattr(data, 'location') and isinstance(data.location, WKBElement):
            point = to_shape(data.location)
            res["latitude"] = point.y
            res["longitude"] = point.x

        return res
