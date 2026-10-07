import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class InventoryResponse(BaseModel):
    product_id: uuid.UUID
    stock: int
    version: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class InventoryUpdate(BaseModel):
    stock: int = Field(..., ge=0, description="The new stock quantity. Must be >= 0.")
    expected_version: int = Field(..., description="The current version of the inventory to prevent race conditions.")
