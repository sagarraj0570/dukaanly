import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Boolean, DateTime, ForeignKey, func, Text, Numeric, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    master_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("master_catalog_items.id", ondelete="SET NULL"), nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Numeric with fixed precision for monetary values
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumb_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    image_license: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_attribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Shop-owner custom upload overrides
    custom_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_thumb_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    shop = relationship("Shop", backref="products")
    master_item = relationship("MasterCatalogItem", back_populates="products")
    inventory = relationship("Inventory", back_populates="product", uselist=False, cascade="all, delete-orphan")
