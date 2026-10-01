from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POS_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./pos.db"
    erp_base_url: str = "http://localhost:8001"
    erp_client_id: str = "pos-dev"
    erp_client_secret: str = "pos-dev-secret"
    erp_app_code: str = "POS"
    # After this many failed pushes an order stops retrying and needs a manual push.
    push_max_attempts: int = 8
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
