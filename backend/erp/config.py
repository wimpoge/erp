from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ERP_", env_file=".env", extra="ignore")

    # Neon/Postgres in production, e.g. postgresql+psycopg://user:pass@host/db?sslmode=require
    database_url: str = "sqlite:///./erp.db"
    # Serverless (Vercel): every invocation may be a new process, so don't keep a pool.
    serverless: bool = False
    session_hours: int = 12
    # True behind HTTPS so the session cookie is never sent in clear text.
    cookie_secure: bool = False
    integration_token_ttl_seconds: int = 3600
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
