import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Integer, Numeric, DateTime, ForeignKey, func, CheckConstraint, Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

class OrderStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    preparing = "preparing"
    ready_for_delivery = "ready_for_delivery"
    out_for_delivery = "out_for_delivery"
    delivered = "delivered"
    cancelled = "cancelled"

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    shop_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shops.id", ondelete="RESTRICT"), nullable=False, index=True)
    
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, name="order_status_enum"), default=OrderStatus.pending, nullable=False)
    
    # Monetary values
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    
    # Idempotency key to prevent double charging/ordering
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    customer = relationship("User")
    shop = relationship("Shop")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="chk_order_total_positive"),
        # Ensure that for a given customer, the idempotency_key is unique if provided.
        # Postgres allows multiple NULLs in unique constraints.
        UniqueConstraint('customer_id', 'idempotency_key', name='uq_order_customer_idempotency')
    )

class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    
    # Historical Snapshots
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    
    order = relationship("Order", back_populates="items")
    product = relationship("Product")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_order_item_qty_positive"),
        CheckConstraint("unit_price >= 0", name="chk_order_item_price_positive"),
        CheckConstraint("line_total >= 0", name="chk_order_item_total_positive"),
    )
