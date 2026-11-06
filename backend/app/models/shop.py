import enum
import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime, ForeignKey, func, Text, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.import_batch import ImportBatch

class ShopVerificationStatus(str, enum.Enum):
    discovered = "discovered"
    pending_review = "pending_review"
    verified = "verified"
    rejected = "rejected"
    archived = "archived"

class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Using SRID 4326 for standard lon/lat (WGS 84). 
    # spatial_index=True creates the GiST index automatically
    location = mapped_column(Geometry(geometry_type='POINT', srid=4326, spatial_index=True), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    opening_hours: Mapped[str | None] = mapped_column(String(100), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_orderable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_status: Mapped[ShopVerificationStatus] = mapped_column(
        Enum(ShopVerificationStatus, name="shop_verification_status"),
        default=ShopVerificationStatus.discovered,
        nullable=False
    )

    # Provenance & Batch Tracking
    source: Mapped[str | None] = mapped_column(String(50), default="manual", nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_attribution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True, index=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    import_batch: Mapped[Optional["ImportBatch"]] = relationship("ImportBatch", back_populates="shops")
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

