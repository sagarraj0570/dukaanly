import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Numeric, DateTime, ForeignKey, func, CheckConstraint, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

class PaymentStatus(str, enum.Enum):
    created = "created"
    pending = "pending"
    authorized = "authorized"
    captured = "captured"
    failed = "failed"
    cancelled = "cancelled"
    refunded = "refunded"

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    
    provider: Mapped[str] = mapped_column(String(50), nullable=False) # e.g., "razorpay"
    provider_payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True, unique=True) # e.g., "pay_XXX"
    provider_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True, unique=True) # e.g., "order_XXX"
    
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus, name="payment_status_enum"), default=PaymentStatus.created, nullable=False)
    
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order = relationship("Order")
    
    __table_args__ = (
        CheckConstraint("amount >= 0", name="chk_payment_amount_positive"),
    )
