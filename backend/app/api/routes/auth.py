from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.user import UserCreate, UserResponse
from app.schemas.auth import Token, LoginRequest, RefreshRequest
from app.services import auth as auth_service
from app.models.user import User
from app.api.dependencies import get_current_user

router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new customer."""
    return await auth_service.register_user(db=db, user_in=user_in)

@router.post("/login", response_model=Token)
async def login(login_data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return access & refresh tokens."""
    user = await auth_service.authenticate_user(db=db, email=login_data.email, password=login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
        
    return await auth_service.create_tokens_for_user(db=db, user=user)

@router.post("/refresh", response_model=Token)
async def refresh(refresh_data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Rotate refresh token and issue new access token."""
    return await auth_service.refresh_tokens(db=db, raw_refresh_token=refresh_data.refresh_token)

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(refresh_data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Revoke the given refresh token."""
    await auth_service.logout_user(db=db, raw_refresh_token=refresh_data.refresh_token)

@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user."""
    return current_user
