import uuid
import typing
from pydantic import BaseModel, ConfigDict, Field, model_validator
from datetime import datetime
from app.models.delivery import DeliveryStatus

class DeliveryCreate(BaseModel):
    order_id: uuid.UUID
    destination_latitude: float | None = Field(None, ge=-90.0, le=90.0)
    destination_longitude: float | None = Field(None, ge=-180.0, le=180.0)

class DeliveryAssign(BaseModel):
    rider_id: uuid.UUID

class DeliveryStatusUpdate(BaseModel):
    status: DeliveryStatus

class DeliveryResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    rider_id: uuid.UUID | None
    status: DeliveryStatus
    destination_latitude: float | None = None
    destination_longitude: float | None = None
    assigned_at: datetime | None
    picked_up_at: datetime | None
    delivered_at: datetime | None
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
            "order_id": data.order_id,
            "rider_id": data.rider_id,
            "status": data.status,
            "assigned_at": data.assigned_at,
            "picked_up_at": data.picked_up_at,
            "delivered_at": data.delivered_at,
            "created_at": data.created_at,
            "updated_at": data.updated_at,
        }

        if hasattr(data, 'destination_location') and isinstance(data.destination_location, WKBElement):
            point = to_shape(data.destination_location)
            res["destination_latitude"] = point.y
            res["destination_longitude"] = point.x

        return res

class RiderCandidateResponse(BaseModel):
    rider_id: uuid.UUID
    distance_meters: float
    is_available: bool
    location_updated_at: datetime | None

