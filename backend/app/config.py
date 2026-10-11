import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./challenge.db")
    db_schema: str = os.getenv("DB_SCHEMA", "")
    secret_key: str = os.getenv("SECRET_KEY", "")
    app_env: str = os.getenv("APP_ENV", "development")
    token_ttl_minutes: int = int(os.getenv("TOKEN_TTL_MINUTES", "120"))


def get_settings() -> Settings:
    settings = Settings()
    if settings.app_env != "development" and len(settings.secret_key) < 32:
        raise RuntimeError("SECRET_KEY must be at least 32 characters outside development")
    return settings
