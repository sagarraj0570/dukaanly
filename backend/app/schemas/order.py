import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Any
from decimal import Decimal
from typing import List

from app.models.order import OrderStatus
from app.models.delivery import DeliveryStatus

class CheckoutRequest(BaseModel):
    idempotency_key: str = Field(..., max_length=100, description="Unique client-generated key to prevent duplicate orders.")
    destination_latitude: float | None = Field(None, ge=-90.0, le=90.0, description="Customer delivery latitude.")
    destination_longitude: float | None = Field(None, ge=-180.0, le=180.0, description="Customer delivery longitude.")

class OrderItemResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID | None
    product_name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal

    model_config = ConfigDict(from_attributes=True)

class OrderDeliverySummary(BaseModel):
    id: uuid.UUID
    status: DeliveryStatus
    rider_id: uuid.UUID | None = None
    assigned_at: datetime | None = None
    picked_up_at: datetime | None = None
    delivered_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

class OrderEventResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    from_state: str
    to_state: str
    actor_id: uuid.UUID | None = None
    actor_role: str
    reason: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class OrderResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    shop_id: uuid.UUID
    status: OrderStatus
    total_amount: Decimal
    items: List[OrderItemResponse]
    created_at: datetime
    updated_at: datetime
    delivery: OrderDeliverySummary | None = None
    events: List[OrderEventResponse] = Field(default_factory=list)
    reservation_expires_at: datetime | None = None
    reservation_status: str | None = None

    model_config = ConfigDict(from_attributes=True)

class ReservationItemResponse(BaseModel):
    product_id: uuid.UUID
    quantity: int
    status: str
    reservation_reference: str

class OrderReservationResponse(BaseModel):
    order_id: uuid.UUID
    status: str
    expires_at: datetime | None = None
    seconds_remaining: int = 0
    server_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_expired: bool = False
    items: List[ReservationItemResponse] = Field(default_factory=list)

class OrderListResponse(BaseModel):
    items: List[OrderResponse]
    total: int
    page: int
    size: int

class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    reason: str | None = Field(None, max_length=500, description="Optional transition or cancellation reason.")

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> Any:
        if v == "ready_for_pickup":
            return OrderStatus.ready_for_delivery
        return v

class OrderCancelRequest(BaseModel):
    reason: str | None = Field(None, max_length=500, description="Optional cancellation reason.")

class OrderRejectRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500, description="Mandatory rejection reason.")
