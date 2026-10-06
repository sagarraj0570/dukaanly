import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.models.user import UserRole

# Shared properties
class UserBase(BaseModel):
    name: str = Field(..., max_length=100)
    email: EmailStr
    phone_number: str | None = Field(None, max_length=20)

# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    role: UserRole = UserRole.customer # Only default, api will handle properly

# Properties to return via API
class UserResponse(UserBase):
    id: uuid.UUID
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
