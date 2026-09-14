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

    # Disables bearer-token authentication and treats every caller as a trusted
    # service principal. `app.core.security` refuses to honour this outside
    # env=local/test, so it cannot silently disable auth in a deployed
    # environment.
    auth_dev_bypass: bool = False

    # Connection pool. Sized for a single-node deployment; Postgres's own
    # max_connections is the ceiling that matters when the worker and API
    # both connect.
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 30
    # Caps a runaway query instead of letting it hold a connection forever.
    db_statement_timeout_ms: int = 10_000

    default_locale: str = "en"
    supported_locales: list[str] = ["en", "ar"]
    default_timezone: str = "Asia/Riyadh"
    default_currency: str = "SAR"
    # GCC country calling codes accepted for phone validation (to verify: full GCC coverage)
    allowed_phone_country_codes: list[str] = ["966", "971", "973", "974", "965", "968"]

    # --- Booking / availability ---
    #: Grid that bookable slots are generated on. 15 minutes is the finest
    #: granularity a salon realistically schedules to; a smaller value multiplies
    #: the number of slots returned without giving the customer a real choice.
    availability_slot_granularity_minutes: int = 15
    #: How far ahead availability may be queried in one request. Unbounded, this
    #: is a cheap way to make the server generate millions of slots.
    availability_max_horizon_days: int = 90
    #: How long an AI-agent or checkout slot hold survives before the slot is
    #: released again (docs/04 section 2A, docs/10 section 5).
    slot_hold_ttl_seconds: int = 300
    booking_free_cancellation_hours: int = 24

    # --- Queue / tickets ---
    #: Virtual tickets expire this long after issue. An indefinitely valid QR
    #: code is a permanent bearer credential.
    ticket_ttl_hours: int = 12
    #: How far a walk-in yields to a booked appointment on the shared provider
    #: timeline. See `queue.domain.priority_key` for what this actually means.
    queue_walk_in_penalty_minutes: int = 15

    # --- Payments ---
    moyasar_api_key: str | None = None
    moyasar_webhook_secret: str | None = None
    moyasar_base_url: str = "https://api.moyasar.com/v1"
    #: Deposit required to confirm a booking, as a percentage of service price.
    #: 0 means bookings confirm without payment (docs/11 allows both).
    default_deposit_percent: int = 0

    # --- Media / Nextcloud ---
    nextcloud_url: str | None = None
    nextcloud_username: str | None = None
    nextcloud_app_password: str | None = None
    nextcloud_root_folder: str = "nova-media"
    media_upload_url_ttl_seconds: int = 900
    media_max_upload_bytes: int = 100 * 1024 * 1024

    # --- Notifications / WhatsApp ---
    whatsapp_bsp_api_key: str | None = None
    whatsapp_bsp_base_url: str | None = None
    whatsapp_phone_number_id: str | None = None
    #: Local-time window during which non-urgent messages are held. GCC norms;
    #: see `notification.domain.is_within_quiet_hours`.
    quiet_hours_start: int = 22
    quiet_hours_end: int = 8

    # --- AI agents (docs/04, docs/10) ---
    #: OpenAI-compatible endpoint. Ollama exposes one at /v1.
    ollama_base_url: str = "http://localhost:11434/v1"
    ai_routing_model: str = "llama3.1:8b"
    ai_reasoning_model: str = "llama3.1:70b"
    #: docs/10 section 12: abort the turn and hand off past this.
    ai_tool_timeout_seconds: float = 5.0
    ai_request_timeout_seconds: float = 30.0
    ai_enabled: bool = True

    # --- Ingress ---
    cloudflare_tunnel_token: str | None = None

    #: Public base URL of the customer PWA. Used to build `ticket_page_url`
    #: (docs/07 section 7) — a ticket the customer cannot open is not a ticket.
    public_app_url: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
