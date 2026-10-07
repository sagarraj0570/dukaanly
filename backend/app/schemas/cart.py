import uuid
from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from typing import List

class CartItemAdd(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(..., gt=0, description="Quantity must be greater than 0")

class CartItemUpdate(BaseModel):
    quantity: int = Field(..., gt=0, description="Quantity must be greater than 0")

class CartItemResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    product_name: str
    product_price: Decimal
    item_total: Decimal

    model_config = ConfigDict(from_attributes=True)

class CartResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    shop_id: uuid.UUID | None
    items: List[CartItemResponse]
    total_amount: Decimal

    model_config = ConfigDict(from_attributes=True)
