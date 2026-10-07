import uuid
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from app.models.delivery import DeliveryStatus

class DeliveryCreate(BaseModel):
    order_id: uuid.UUID

class DeliveryAssign(BaseModel):
    rider_id: uuid.UUID

class DeliveryStatusUpdate(BaseModel):
    status: DeliveryStatus

class DeliveryResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    rider_id: uuid.UUID | None
    status: DeliveryStatus
    assigned_at: datetime | None
    picked_up_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
