import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, func, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

from app.db.base import Base

class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Using SRID 4326 for standard lon/lat (WGS 84). 
    # spatial_index=True creates the GiST index automatically
    location = mapped_column(Geometry(geometry_type='POINT', srid=4326, spatial_index=True), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Note: relationship back_populates can be added to User later if needed, but keeping it simple for now
