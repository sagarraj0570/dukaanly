import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, func, Enum, Index, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

from app.db.base import Base

class DeliveryStatus(str, enum.Enum):
    pending = "pending"
    assigned = "assigned"
    picked_up = "picked_up"
    out_for_delivery = "out_for_delivery"
    delivered = "delivered"
    cancelled = "cancelled"

class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, unique=False, index=True)
    rider_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("rider_profiles.id", ondelete="RESTRICT"), nullable=True, index=True)
    
    status: Mapped[DeliveryStatus] = mapped_column(Enum(DeliveryStatus, name="delivery_status_enum"), default=DeliveryStatus.pending, nullable=False)
    destination_location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Preparation & Smart ETA Snapshot Tracking
    preparation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    preparation_estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eta_earliest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    eta_latest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    eta_calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    eta_remaining_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eta_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    eta_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    eta_delay_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    eta_update_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Automated Proximity Dispatch Tracking (Stage A1)
    dispatch_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    awaiting_rider: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dispatch_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    order = relationship("Order", back_populates="delivery")
    rider = relationship("RiderProfile")
    offers = relationship("DeliveryOffer", back_populates="delivery", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index(
            "idx_active_delivery_per_rider",
            rider_id,
            unique=True,
            postgresql_where=status.in_([DeliveryStatus.assigned, DeliveryStatus.picked_up, DeliveryStatus.out_for_delivery])
        ),
        Index(
            "idx_active_delivery_per_order",
            order_id,
            unique=True,
            postgresql_where=status.in_([
                DeliveryStatus.pending,
                DeliveryStatus.assigned,
                DeliveryStatus.picked_up,
                DeliveryStatus.out_for_delivery,
            ])
        ),
        Index(
            "ix_deliveries_status_assigned_at",
            status,
            assigned_at,
        ),
    )
