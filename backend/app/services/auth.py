from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
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

async def create_tokens_for_user(
    db: AsyncSession,
    user: User,
    family_id: Optional[uuid.UUID] = None,
) -> Token:
    access_token = security.create_access_token(subject=str(user.id), role=user.role.value)
    
    raw_refresh_token = security.create_refresh_token()
    token_hash = security.hash_refresh_token(raw_refresh_token)
    
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    token_family = family_id or uuid.uuid4()
    
    db_refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        family_id=token_family,
        expires_at=expires_at,
    )
    
    # Update last login
    user.last_login = datetime.now(timezone.utc)
    
    db.add(db_refresh_token)
    await db.commit()
    
    return Token(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        token_type="bearer",
    )

async def refresh_tokens(db: AsyncSession, raw_refresh_token: str) -> Token:
    token_hash = security.hash_refresh_token(raw_refresh_token)
    now = datetime.now(timezone.utc)
    
    # 1. Query with row-level lock to prevent concurrent refresh races creating multiple valid sessions
    stmt = (
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .with_for_update()
    )
    result = await db.execute(stmt)
    db_token = result.scalar_one_or_none()
    
    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
        
    # Check for token reuse (revocation)
    if db_token.revoked_at is not None:
        # Tightened 5-second grace window for concurrent in-flight requests
        # Returns 401 without revoking the family, avoiding killing the legitimate user's session
        grace_seconds = 5.0
        time_since_revocation = (now - db_token.revoked_at).total_seconds()
        if 0 <= time_since_revocation <= grace_seconds and db_token.replaced_by_id is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token already refreshed",
            )
            
        # Outside grace window or no child replacement: Confirmed token reuse attack!
        # Immediately revoke all tokens in this token family
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == db_token.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token reuse detected. All sessions in this family have been revoked.",
        )
        
    if db_token.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )
        
    # Get user
    stmt = select(User).where(User.id == db_token.user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User inactive or deleted",
        )
        
    # Rotate token: revoke old one
    db_token.revoked_at = now
    
    # Generate new refresh token in the same family
    new_raw_token = security.create_refresh_token()
    new_token_hash = security.hash_refresh_token(new_raw_token)
    new_expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    new_db_token = RefreshToken(
        user_id=user.id,
        token_hash=new_token_hash,
        family_id=db_token.family_id,
        expires_at=new_expires_at,
    )
    db.add(new_db_token)
    await db.flush()
    
    # Link old token to the newly issued successor
    db_token.replaced_by_id = new_db_token.id
    await db.commit()
    
    access_token = security.create_access_token(subject=str(user.id), role=user.role.value)
    
    token_response = Token(
        access_token=access_token,
        refresh_token=new_raw_token,
        token_type="bearer",
    )

    return token_response

async def logout_user(db: AsyncSession, raw_refresh_token: str):
    token_hash = security.hash_refresh_token(raw_refresh_token)
    
    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    result = await db.execute(stmt)
    db_token = result.scalar_one_or_none()
    
    if db_token:
        now = datetime.now(timezone.utc)
        # Server-side revocation of the entire token family
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == db_token.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await db.commit()
