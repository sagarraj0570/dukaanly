import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, ForeignKey, DateTime, func, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    
    # Notification metadata
    type: Mapped[str] = mapped_column(String(50), index=True)  # e.g. "ORDER_STATUS_CHANGED", "DELIVERY_UPDATE"
    reference_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)  # e.g. order_id or delivery_id
    
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(String)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="notifications")
