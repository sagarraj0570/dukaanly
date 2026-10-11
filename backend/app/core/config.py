import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, model_validator

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

class Settings(BaseSettings):
    APP_NAME: str = "Dukaanly API"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    
    ALLOWED_ORIGINS: str = "http://localhost:5173"
    
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433
    POSTGRES_DB: str = "dukaanly"
    POSTGRES_USER: str = "dukaanly_user"
    POSTGRES_PASSWORD: str = ""
    DATABASE_URL: str | None = None
    
    REDIS_URL: str = "redis://localhost:6379/0"
    
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
    RIDER_LOCATION_MAX_AGE_SECONDS: int = 900
    RIDER_LOCATION_MIN_UPDATE_INTERVAL_SECONDS: float = 1.0

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
        return self


    model_config = ConfigDict(env_file=str(ROOT_DIR / ".env"), extra="ignore")

settings = Settings()
