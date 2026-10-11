import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from typing import List

from app.models.order import OrderStatus
from app.models.delivery import DeliveryStatus

class CheckoutRequest(BaseModel):
    idempotency_key: str = Field(..., max_length=100, description="Unique client-generated key to prevent duplicate orders.")

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

    model_config = ConfigDict(from_attributes=True)

class OrderListResponse(BaseModel):
    items: List[OrderResponse]
    total: int
    page: int
    size: int

class OrderStatusUpdate(BaseModel):
    status: OrderStatus
