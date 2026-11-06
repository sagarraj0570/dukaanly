import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func, Text, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

class MasterCatalogItem(Base):
    __tablename__ = "master_catalog_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumb_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    image_license: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_attribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    products = relationship("Product", back_populates="master_item")
