import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, func, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DeliveryOfferStatus(str, enum.Enum):
    offered = "offered"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"
    cancelled = "cancelled"


class DeliveryOffer(Base):
    __tablename__ = "delivery_offers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deliveries.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    rider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rider_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=DeliveryOfferStatus.offered.value, nullable=False)
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    delivery = relationship("Delivery", back_populates="offers")
    rider = relationship("RiderProfile")

    __table_args__ = (
        CheckConstraint(
            "status IN ('offered', 'accepted', 'declined', 'expired', 'cancelled')",
            name="chk_delivery_offer_status"
        ),
        UniqueConstraint("delivery_id", "rider_id", "attempt_no", name="uq_delivery_offers_attempt"),
        Index("ix_delivery_offers_rider_open", "rider_id", "status", "expires_at"),
        Index("ix_delivery_offers_delivery_status", "delivery_id", "status"),
    )
