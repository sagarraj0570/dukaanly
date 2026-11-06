import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, func, CheckConstraint, Enum, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

class ReservationStatus(str, enum.Enum):
    active = "active"
    consumed = "consumed"
    released = "released"
    expired = "expired"

class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reservation_reference: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus, name="reservation_status_enum"),
        default=ReservationStatus.active,
        nullable=False,
        index=True
    )
    
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    release_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    order = relationship("Order", back_populates="reservations")
    product = relationship("Product")
    customer = relationship("User")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_reservation_quantity_positive"),
        Index("ix_inv_res_status_expires_at", "status", "expires_at"),
    )
