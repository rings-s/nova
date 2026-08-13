from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = True

    database_url: PostgresDsn
    redis_url: RedisDsn
    secret_key: str

    cors_origins: list[str] = ["http://localhost:5173"]

    default_locale: str = "en"
    supported_locales: list[str] = ["en", "ar"]
    default_timezone: str = "Asia/Riyadh"
    default_currency: str = "SAR"
    # GCC country calling codes accepted for phone validation (to verify: full GCC coverage)
    allowed_phone_country_codes: list[str] = ["966", "971", "973", "974", "965", "968"]

    # --- Reserved for future integration adapters. Unused until an adapter is implemented. ---
    whatsapp_bsp_api_key: str | None = None
    moyasar_api_key: str | None = None
    nextcloud_url: str | None = None
    nextcloud_username: str | None = None
    nextcloud_app_password: str | None = None
    cloudflare_tunnel_token: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
