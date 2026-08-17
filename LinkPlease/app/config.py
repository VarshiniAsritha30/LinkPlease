"""Application configuration settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    PSEUDOGRAM_API_BASE_URL: str = "https://pseudogram-api.onrender.com"
    PSEUDOGRAM_API_KEY: str = ""
    DATABASE_URL: str = "sqlite+aiosqlite:///./linkplease.db"
    WEBHOOK_SIGNATURE_REQUIRED: bool = False
    MAX_DM_ATTEMPTS: int = 5
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str) -> str:
        if isinstance(v, str):
            # Ensure SQLite uses aiosqlite for async engine
            if v.startswith("sqlite:///") and not v.startswith("sqlite+aiosqlite:///"):
                return v.replace("sqlite:///", "sqlite+aiosqlite:///")
            # Ensure PostgreSQL uses asyncpg for async engine
            if v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
                return v.replace("postgresql://", "postgresql+asyncpg://")
        return v


settings = Settings()
