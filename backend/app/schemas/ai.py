"""
Pydantic v2 schemas for the Dukaanly AI Shopping Assistant.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.catalog_search import CatalogProductItem


class ShoppingChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1, max_length=1000)

    model_config = ConfigDict(extra="ignore")


class ShoppingAssistantRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500, description="Customer natural language shopping request")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Customer delivery latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Customer delivery longitude")
    shop_id: Optional[uuid.UUID] = Field(None, description="Optional shop filter constraint")
    history: List[ShoppingChatMessage] = Field(default_factory=list, max_length=10, description="Recent conversation turns")

    model_config = ConfigDict(extra="ignore")

    @classmethod
    def sanitize_string(cls, text: str) -> str:
        # Strip non-printable control characters except whitespace
        sanitized = "".join(ch for ch in text if ch.isprintable() or ch in ("\n", " ")).strip()
        return sanitized

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        cleaned = "".join(ch for ch in v if ch.isprintable() or ch in ("\n", " ")).strip()
        if not cleaned:
            raise ValueError("Message cannot be blank or contain only control characters.")
        return cleaned[:500]


class ProposedCartItem(BaseModel):
    product_id: uuid.UUID
    product_name: str
    quantity: int = Field(..., ge=1, le=50)
    unit_price: Decimal = Field(..., ge=Decimal("0.00"))
    item_total: Decimal = Field(..., ge=Decimal("0.00"))
    available_stock: int = Field(..., ge=1)
    image_url: Optional[str] = None
    thumb_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ProposedCart(BaseModel):
    shop_id: uuid.UUID
    shop_name: str
    shop_address: str
    distance_meters: float
    items: List[ProposedCartItem]
    total_amount: Decimal = Field(..., ge=Decimal("0.00"))
    is_delivery_eligible: bool = True
    has_different_shop_in_current_cart: bool = False
    warning_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ShoppingAssistantResponse(BaseModel):
    assistant_message: str
    clarifying_question: Optional[str] = None
    matched_products: List[CatalogProductItem] = Field(default_factory=list)
    proposed_cart: Optional[ProposedCart] = None
    search_query_used: Optional[str] = None
    provider: str
    model: str
    latency_ms: float

    model_config = ConfigDict(from_attributes=True)
