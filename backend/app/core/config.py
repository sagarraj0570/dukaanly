import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

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
    
    REDIS_URL: str = "redis://localhost:6379/0"

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        
    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    model_config = ConfigDict(env_file=str(ROOT_DIR / ".env"), extra="ignore")

settings = Settings()
