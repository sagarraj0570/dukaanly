import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, model_validator

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

class Settings(BaseSettings):
    APP_NAME: str = "Dukaanly API"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433
    POSTGRES_DB: str = "dukaanly"
    POSTGRES_USER: str = "dukaanly_user"
    POSTGRES_PASSWORD: str = ""
    DATABASE_URL: str | None = None

    # Database Connection Pool Resilience (Stage 9)
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: float = 30.0
    DB_POOL_RECYCLE: int = 1800  # 30 minutes to eliminate stale connection drops
    DB_POOL_PRE_PING: bool = True  # Detect dead/dropped connections before checkout
    DB_CONNECT_TIMEOUT: float = 5.0
    
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: str | None = None

    # Redis Resilience (Stage 9)
    REDIS_SOCKET_TIMEOUT: float = 3.0
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 3.0
    REDIS_MAX_CONNECTIONS: int = 50

    # Graceful Shutdown & Observability (Stage 9)
    GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS: float = 15.0
    LOG_FORMAT: str = "json"  # "json" or "text"

    # Rate Limiting Settings
    AUTH_RATE_LIMIT_LOGIN_PER_MINUTE: int = 20
    AUTH_RATE_LIMIT_LOGIN_ACCOUNT_PER_MINUTE: int = 10
    AUTH_RATE_LIMIT_REGISTER_PER_MINUTE: int = 20
    AUTH_RATE_LIMIT_REFRESH_PER_MINUTE: int = 30
    CHECKOUT_RATE_LIMIT_PER_MINUTE: int = 15
    RATE_LIMIT_FAIL_CLOSED: bool = False
    RATE_LIMIT_AUTH_FAIL_CLOSED: bool = False
    RATE_LIMIT_DEGRADED_WORKER_FACTOR: int = 4

    # Reverse Proxy & Trusted Forwarding Settings
    FORWARDED_ALLOW_IPS: str = "*"
    TRUSTED_PROXIES: str = "127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    
    JWT_SECRET_KEY: str = "supersecret_for_development_only"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Payment Settings
    PAYMENT_PROVIDER: str = "razorpay"
    ALLOW_MOCK_PAYMENTS: bool = False
    RAZORPAY_KEY_ID: str | None = None
    RAZORPAY_KEY_SECRET: str | None = None
    RAZORPAY_WEBHOOK_SECRET: str | None = None
    CURRENCY: str = "INR"

    # Rider & Geospatial
    RIDER_SEARCH_RADIUS_METERS: int = 5000
    RIDER_LOCATION_MAX_AGE_SECONDS: int = 120
    RIDER_LOCATION_MIN_UPDATE_INTERVAL_SECONDS: float = 1.0

    # Automated Proximity Dispatch (Stage A)
    DISPATCH_AUTO_ENABLED: bool = True
    DISPATCH_OFFER_TTL_SECONDS: int = 30
    DISPATCH_MAX_ATTEMPTS: int = 3
    DISPATCH_BATCH_SIZE: int = 5
    DISPATCH_TRIGGER: str = "confirmed"
    DISPATCH_ATTEMPT_1_RADIUS_METERS: int = 3000
    DISPATCH_ATTEMPT_2_RADIUS_METERS: int = 5000

    # Geoapify Places API Settings
    GEOAPIFY_API_KEY: str | None = None
    GEOAPIFY_BASE_URL: str = "https://api.geoapify.com/v2/places"
    GEOAPIFY_CACHE_TTL_SECONDS: int = 300
    GEOAPIFY_REQUEST_TIMEOUT_SECONDS: float = 8.0

    # Routing Infrastructure Settings
    ROUTING_PROVIDER: str = "osrm"
    OSRM_BASE_URL: str = "http://localhost:5000"
    OSRM_TIMEOUT_SECONDS: float = 4.0
    OSRM_REQUEST_TIMEOUT_SECONDS: float = 4.0
    OSRM_CACHE_TTL_SECONDS: int = 300
    OSRM_MAX_CONCURRENT_REQUESTS: int = 10
    RIDER_MAX_CANDIDATES_TO_ROUTE: int = 5

    # Smart Delivery ETA Settings
    ETA_DEFAULT_PREPARATION_MINUTES: int = 10
    ETA_ASSIGNMENT_WAIT_BUFFER_SECONDS: int = 180
    ETA_PICKUP_BUFFER_SECONDS: int = 180
    ETA_DROPOFF_BUFFER_SECONDS: int = 180
    ETA_UNCERTAINTY_BUFFER_SECONDS: int = 300
    ETA_MIN_RECALC_INTERVAL_SECONDS: int = 30
    ETA_REROUTE_MOVEMENT_METERS: float = 50.0
    ETA_MAX_SNAPSHOT_AGE_SECONDS: int = 180

    # Order & Delivery Lifecycle Recovery Settings (Stage 6 & 8)
    ORDER_PENDING_TIMEOUT_SECONDS: int = 900  # 15 minutes to complete payment
    INVENTORY_RESERVATION_TTL_SECONDS: int = 900  # 15 minutes stock reservation TTL (Stage 8)
    ORDER_CONFIRMED_TIMEOUT_SECONDS: int = 1800  # 30 minutes for shop to accept/prepare
    DELIVERY_ASSIGNED_TIMEOUT_SECONDS: int = 900  # 15 minutes for assigned rider to pickup
    ORDER_RECOVERY_BATCH_SIZE: int = 50
    ORDER_RECOVERY_LOCK_TIMEOUT_SECONDS: float = 5.0
    PAYMENT_RECONCILIATION_GRACE_SECONDS: int = 120  # 2 minutes grace period for in-flight reconciliation
    PAYMENT_MAX_RECONCILIATION_RETAIN_SECONDS: int = 600  # 10 minutes max retention for ambiguous payment outcomes

    # AI Foundation Settings
    AI_ENABLED: bool = False
    AI_PROVIDER: str = "mock"  # "mock", "openai", "openrouter", "groq", "gemini"
    AI_API_KEY: str | None = None
    AI_BASE_URL: str = "https://api.openai.com/v1"
    AI_MODEL: str = "gpt-4o-mini"
    AI_REQUEST_TIMEOUT_SECONDS: float = 10.0
    AI_MAX_TOKENS: int = 1000
    AI_TEMPERATURE: float = 0.2
    AI_MAX_RETRIES: int = 2
    AI_RETRY_BACKOFF_SECONDS: float = 0.5
    AI_RATE_LIMIT_PER_MINUTE: int = 20
    AI_MAX_CONCURRENT_REQUESTS: int = 5

    # Provider-Specific API Keys (Loaded from .env; never exposed or committed)
    GROQ_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None

    # AI Feature Flags
    AI_FEATURE_SHOPPING_ASSISTANT: bool = False
    AI_FEATURE_CATALOG_SEARCH: bool = False
    AI_FEATURE_ORDER_SUPPORT: bool = False

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        
    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def redis_url_masked(self) -> str:
        from app.core.redis import mask_redis_url
        return mask_redis_url(self.REDIS_URL)

    @model_validator(mode="after")
    def assemble_redis_url(self) -> "Settings":
        if self.REDIS_URL and "localhost" in self.REDIS_URL:
            # Normalize 'localhost' to IPv4 '127.0.0.1' to prevent IPv6 loopback connection timeouts on Windows
            self.REDIS_URL = self.REDIS_URL.replace("@localhost", "@127.0.0.1").replace("://localhost", "://127.0.0.1")
        if self.REDIS_PASSWORD and self.REDIS_URL:
            parsed = urlsplit(self.REDIS_URL)
            if not parsed.password:
                user = parsed.username or ""
                host = parsed.hostname or "127.0.0.1"
                port = f":{parsed.port}" if parsed.port else ""
                netloc = f"{user}:{self.REDIS_PASSWORD}@{host}{port}"
                self.REDIS_URL = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
        return self

    @model_validator(mode="after")
    def validate_production_env(self) -> "Settings":
        if self.APP_ENV == "development":
            if "ALLOW_MOCK_PAYMENTS" not in self.model_fields_set:
                self.ALLOW_MOCK_PAYMENTS = True
        elif self.APP_ENV == "production":
            if self.JWT_SECRET_KEY == "supersecret_for_development_only" or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError("In production, JWT_SECRET_KEY must be a strong random secret of at least 32 characters.")
            if self.DEBUG:
                raise ValueError("DEBUG mode must be False in production.")
            if self.ALLOW_MOCK_PAYMENTS:
                raise ValueError("ALLOW_MOCK_PAYMENTS cannot be enabled in production. Mock payments are strictly forbidden in production.")
            if not self.OSRM_BASE_URL or "router.project-osrm.org" in self.OSRM_BASE_URL:
                raise ValueError(
                    "In production, OSRM_BASE_URL must not point to the public demo endpoint (router.project-osrm.org). "
                    "Configure an internal self-hosted routing service (e.g. http://osrm:5000) or an approved dedicated routing provider."
                )
        return self


    model_config = ConfigDict(
        env_file=[str(ROOT_DIR / ".env"), str(ROOT_DIR / "backend" / ".env")],
        extra="ignore",
    )

settings = Settings()
