from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.user import UserCreate, UserResponse
from app.schemas.auth import Token, LoginRequest, RefreshRequest
from app.services import auth as auth_service
from app.models.user import User
from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.rate_limit import (
    get_client_ip,
    login_ip_rate_limiter,
    login_email_rate_limiter,
    register_rate_limiter,
    refresh_rate_limiter,
)

router = APIRouter()

REFRESH_COOKIE_NAME = "dukaanly_refresh_token"


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
    is_secure = settings.APP_ENV == "production"
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path="/api/v1/auth",
        max_age=max_age,
    )


def _clear_refresh_cookie(response: Response) -> None:
    is_secure = settings.APP_ENV == "production"
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/api/v1/auth",
        httponly=True,
        secure=is_secure,
        samesite="lax",
    )


def verify_cookie_csrf(request: Request, raw_token_from_body: Optional[str]) -> None:
    """
    If authentication relies on the ambient HttpOnly cookie rather than an explicit JSON body,
    verify that the request Origin/Referer matches a trusted CORS origin.
    This provides defense-in-depth CSRF protection against cross-site attacks.
    """
    # Explicit bearer credentials in JSON payload are not vulnerable to ambient browser CSRF
    if raw_token_from_body:
        return

    origin = request.headers.get("origin")
    if not origin:
        referer = request.headers.get("referer")
        if referer:
            from urllib.parse import urlparse
            parsed = urlparse(referer)
            origin = f"{parsed.scheme}://{parsed.netloc}"

    if not origin:
        return  # Server-to-server or test client without Origin header

    allowed_origins = [o.rstrip("/") for o in settings.cors_origins]
    host = request.headers.get("host")
    if host:
        allowed_origins.extend([f"http://{host}", f"https://{host}"])

    if origin.rstrip("/") not in allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-origin request rejected. Untrusted Origin header for cookie-authenticated request.",
        )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(request: Request, user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new customer."""
    client_ip = get_client_ip(request)
    allowed, retry_after = await register_rate_limiter.check_and_record(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts from this IP address. Please try again later.",
            headers={"Retry-After": str(int(retry_after or 60))},
        )
    return await auth_service.register_user(db=db, user_in=user_in)


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    response: Response,
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user and return access & refresh tokens."""
    client_ip = get_client_ip(request)
    ip_allowed, ip_retry_after = await login_ip_rate_limiter.check_and_record(client_ip)
    if not ip_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts from this IP address. Please try again later.",
            headers={"Retry-After": str(int(ip_retry_after or 60))},
        )

    normalized_email = login_data.email.strip().lower()
    email_allowed, email_retry_after = await login_email_rate_limiter.check_and_record(normalized_email)
    if not email_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts for this account. Please try again later.",
            headers={"Retry-After": str(int(email_retry_after or 60))},
        )

    user = await auth_service.authenticate_user(db=db, email=login_data.email, password=login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    # On successful authentication, reset the account-specific rate limit counter
    await login_email_rate_limiter.reset(normalized_email)

    tokens = await auth_service.create_tokens_for_user(db=db, user=user)
    _set_refresh_cookie(response, tokens.refresh_token)
    return tokens


@router.post("/refresh", response_model=Token)
async def refresh(
    request: Request,
    response: Response,
    refresh_data: Optional[RefreshRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """Rotate refresh token and issue new access token."""
    client_ip = get_client_ip(request)
    allowed, retry_after = await refresh_rate_limiter.check_and_record(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many refresh attempts from this IP address. Please try again later.",
            headers={"Retry-After": str(int(retry_after or 60))},
        )

    raw_token_from_body = refresh_data.refresh_token if refresh_data and refresh_data.refresh_token else None
    verify_cookie_csrf(request, raw_token_from_body)

    raw_token = raw_token_from_body or request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required",
        )

    new_tokens = await auth_service.refresh_tokens(db=db, raw_refresh_token=raw_token)
    _set_refresh_cookie(response, new_tokens.refresh_token)
    return new_tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    refresh_data: Optional[RefreshRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """Revoke the given refresh token and invalidate the associated session."""
    raw_token_from_body = refresh_data.refresh_token if refresh_data and refresh_data.refresh_token else None
    verify_cookie_csrf(request, raw_token_from_body)

    raw_token = raw_token_from_body or request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_token:
        await auth_service.logout_user(db=db, raw_refresh_token=raw_token)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user."""
    return current_user
