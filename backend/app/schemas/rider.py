import uuid
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class RiderAvailabilityUpdate(BaseModel):
    is_available: bool

class RiderProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    is_available: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
