import uuid
from pydantic import BaseModel, ConfigDict
from decimal import Decimal
from datetime import datetime
from app.models.payment import PaymentStatus

class PaymentInitiationResponse(BaseModel):
    payment_id: uuid.UUID
    order_id: uuid.UUID
    provider: str
    provider_order_id: str
    amount: Decimal
    currency: str
    key_id: str | None = None # Public key for frontend SDK

class PaymentVerificationRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

class PaymentResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    provider: str
    provider_payment_id: str | None
    amount: Decimal
    currency: str
    status: PaymentStatus
    created_at: datetime
    paid_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
