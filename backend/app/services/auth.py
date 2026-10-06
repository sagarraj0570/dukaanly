from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
import uuid

from app.models.user import User, RefreshToken, UserRole
from app.schemas.user import UserCreate
from app.schemas.auth import Token
from app.core import security
from app.core.config import settings

async def register_user(db: AsyncSession, user_in: UserCreate) -> User:
    # Normalize email
    email = user_in.email.lower().strip()
    
    # Check existing user
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The user with this email already exists in the system."
        )
    
    # Force default role to customer to prevent privilege escalation via API
    # (If a different registration endpoint is needed for shops/riders, it can be created later)
    user_role = UserRole.customer

    # Create new user
    db_user = User(
        name=user_in.name,
        email=email,
        phone_number=user_in.phone_number,
        password_hash=security.get_password_hash(user_in.password),
        role=user_role,
        is_active=True,
    )
    db.add(db_user)
    try:
        await db.commit()
        await db.refresh(db_user)
        return db_user
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error registering user (possibly duplicate phone number)."
        )

async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    stmt = select(User).where(User.email == email.lower().strip())
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        return None
    if not security.verify_password(password, user.password_hash):
        return None
    return user

async def create_tokens_for_user(db: AsyncSession, user: User) -> Token:
    access_token = security.create_access_token(subject=str(user.id), role=user.role.value)
    
    raw_refresh_token = security.create_refresh_token()
    token_hash = security.hash_refresh_token(raw_refresh_token)
    
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    db_refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at
    )
    
    # Update last login
    user.last_login = datetime.now(timezone.utc)
    
    db.add(db_refresh_token)
    await db.commit()
    
    return Token(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        token_type="bearer"
    )

async def refresh_tokens(db: AsyncSession, raw_refresh_token: str) -> Token:
    token_hash = security.hash_refresh_token(raw_refresh_token)
    
    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    result = await db.execute(stmt)
    db_token = result.scalar_one_or_none()
    
    if not db_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
        
    if db_token.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked")
        
    if db_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")
        
    # Get user
    stmt = select(User).where(User.id == db_token.user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or deleted")
        
    # Rotate token: revoke old one
    db_token.revoked_at = datetime.now(timezone.utc)
    db.add(db_token)
    
    # Return new pair
    return await create_tokens_for_user(db, user)

async def logout_user(db: AsyncSession, raw_refresh_token: str):
    token_hash = security.hash_refresh_token(raw_refresh_token)
    
    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    result = await db.execute(stmt)
    db_token = result.scalar_one_or_none()
    
    if db_token and not db_token.revoked_at:
        db_token.revoked_at = datetime.now(timezone.utc)
        db.add(db_token)
        await db.commit()
