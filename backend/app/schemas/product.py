from pydantic import BaseModel, Field, ConfigDict
import uuid
from datetime import datetime
from decimal import Decimal

class ProductBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    category: str | None = Field(None, max_length=100)
    barcode: str | None = Field(None, max_length=100)
    price: Decimal = Field(..., ge=0, decimal_places=2)
    image_url: str | None = None
    thumb_url: str | None = None

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    description: str | None = None
    category: str | None = Field(None, max_length=100)
    barcode: str | None = Field(None, max_length=100)
    price: Decimal | None = Field(None, ge=0, decimal_places=2)
    image_url: str | None = None
    thumb_url: str | None = None
    is_active: bool | None = None

class ProductResponse(ProductBase):
    id: uuid.UUID
    shop_id: uuid.UUID
    master_item_id: uuid.UUID | None = None
    image_source: str | None = None
    image_license: str | None = None
    image_attribution: str | None = None
    image_source_url: str | None = None
    image_match_confidence: float | None = None
    image_reviewed: bool = False
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    size: int
