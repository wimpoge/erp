from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ERP_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./erp.db"
    token_ttl_seconds: int = 3600
    # Share of sales-order POSTs answered with 503, to demo the POS retry queue.
    fail_rate: float = 0.0
    # API client created by the seed command; the POS uses these credentials.
    client_id: str = "pos-dev"
    client_secret: str = "pos-dev-secret"
    app_code: str = "POS"


@lru_cache
def get_settings() -> Settings:
    return Settings()
