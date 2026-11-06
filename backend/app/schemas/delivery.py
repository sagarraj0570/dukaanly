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
    reason: str | None = Field(None, max_length=500)

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
    preparation_started_at: datetime | None = None
    preparation_estimated_minutes: int | None = None
    eta_earliest_at: datetime | None = None
    eta_latest_at: datetime | None = None
    eta_calculated_at: datetime | None = None
    eta_remaining_seconds: int | None = None
    eta_source: str | None = None
    eta_delay_reason: str | None = None
    eta_update_reason: str | None = None
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
            "preparation_started_at": getattr(data, "preparation_started_at", None),
            "preparation_estimated_minutes": getattr(data, "preparation_estimated_minutes", None),
            "eta_earliest_at": getattr(data, "eta_earliest_at", None),
            "eta_latest_at": getattr(data, "eta_latest_at", None),
            "eta_calculated_at": getattr(data, "eta_calculated_at", None),
            "eta_remaining_seconds": getattr(data, "eta_remaining_seconds", None),
            "eta_source": getattr(data, "eta_source", None),
            "eta_delay_reason": getattr(data, "eta_delay_reason", None),
            "eta_update_reason": getattr(data, "eta_update_reason", None),
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
    road_distance_meters: float | None = None
    estimated_duration_seconds: float | None = None
    estimated_duration_minutes: float | None = None
    is_available: bool
    location_updated_at: datetime | None
    routing_status: str = "straight_line_fallback"


class RouteLegResponse(BaseModel):
    from_name: str
    to_name: str
    from_latitude: float
    from_longitude: float
    to_latitude: float
    to_longitude: float
    distance_meters: float
    duration_seconds: float
    duration_minutes: float
    geometry: list[list[float]]
    is_fallback: bool
    cached: bool


class DeliveryRouteLocation(BaseModel):
    latitude: float
    longitude: float
    name: str


class DeliveryRouteResponse(BaseModel):
    delivery_id: uuid.UUID
    status: DeliveryStatus
    rider_location: DeliveryRouteLocation | None = None
    shop_location: DeliveryRouteLocation
    customer_location: DeliveryRouteLocation
    legs: list[RouteLegResponse]
    total_distance_meters: float
    total_duration_seconds: float
    total_duration_minutes: float
    combined_geometry: list[list[float]]
    active_leg_index: int
    is_fallback: bool
    cached: bool
    attribution: str


class DeliveryEtaDetail(BaseModel):
    earliest_at: datetime | None = None
    latest_at: datetime | None = None
    remaining_seconds: int = 0
    source: str = "osrm"  # "osrm", "fallback_estimate", "unavailable"
    is_estimated: bool = True
    calculated_at: datetime | None = None


class DeliveryEtaBreakdown(BaseModel):
    preparation_remaining_seconds: int = 0
    assignment_wait_seconds: int = 0
    pickup_travel_remaining_seconds: int = 0
    pickup_buffer_seconds: int = 0
    dropoff_travel_seconds: int = 0
    handoff_buffer_seconds: int = 0


class DeliveryEtaResponse(BaseModel):
    delivery_id: uuid.UUID
    status: DeliveryStatus
    eta: DeliveryEtaDetail
    breakdown: DeliveryEtaBreakdown
    update_reason: str | None = None
    delay_explanation: str | None = None


class DeliveryPreparationUpdate(BaseModel):
    estimated_minutes: int = Field(ge=1, le=180, description="Estimated preparation duration in minutes")
    started_at: datetime | None = None
    delay_reason: str | None = None


class OfferShopInfo(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    latitude: float | None = None
    longitude: float | None = None


class RiderOfferResponse(BaseModel):
    id: uuid.UUID
    delivery_id: uuid.UUID
    shop: OfferShopInfo
    pickup_distance_meters: float
    estimated_earnings: float
    expires_at: datetime
    seconds_remaining: int
    offered_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OfferDeclineResponse(BaseModel):
    id: uuid.UUID
    status: str
    responded_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class OfferAcceptResponse(BaseModel):
    id: uuid.UUID
    delivery_id: uuid.UUID
    status: str
    responded_at: datetime | None = None
    assigned_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


