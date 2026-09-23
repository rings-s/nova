from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: The environments where a developer convenience may relax a deployed rule.
DEVELOPMENT_ENVS = frozenset({"local", "test"})

#: The shortest SECRET_KEY a deployed environment accepts. `openssl rand -hex 32`
#: produces 64 characters.
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    #: Production unless told otherwise, so a deployment that forgets ENV gets
    #: the strict rules (SECRET_KEY checked, no dev bypass, an RLS-exempt
    #: database role refused) instead of the relaxed local ones.
    env: Literal["local", "test", "staging", "production"] = "production"
    debug: bool = True

    database_url: PostgresDsn
    #: The schema owner, for Alembic alone. The API and worker connect as
    #: `database_url`'s role, which row-level security must apply to (see
    #: `app.db.session.enforce_rls_role`), and that role cannot create tables.
    #: Unset, migrations use `database_url` too.
    migration_database_url: PostgresDsn | None = None
    redis_url: RedisDsn
    secret_key: str

    cors_origins: list[str] = ["http://localhost:5173"]

    # Disables bearer-token authentication and treats every caller as a trusted
    # service principal. Settings refuses to load with it on outside
    # env=local/test or while a tunnel token is set (`dev_bypass_refusal`), and
    # `app.core.security` checks the same rule again per request.
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
    #: How many slots one customer may hold at one tenant at once. A hold blocks
    #: the slot for everyone, so an uncapped customer could keep a salon's whole
    #: calendar unbookable. Staff are not capped.
    slot_hold_max_active_per_customer: int = 3
    booking_free_cancellation_hours: int = 24

    # --- Public marketplace (ADR-0010) ---
    #: How much calendar one anonymous availability request may ask for. Much
    #: shorter than `availability_max_horizon_days`, because the public route
    #: answers for every provider qualified for the service rather than one
    #: named provider, so the same window costs a multiple of it.
    discovery_max_availability_days: int = 14
    #: Hard cap on slots in one public availability response. The window bounds
    #: the date dimension; a salon with thirty stylists is the other one.
    discovery_max_public_slots: int = 500

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
    #: How long a conversation's recent turns are remembered, and how many
    #: (`ai_agents/history.py`). Working memory for the model, not a record.
    ai_history_ttl_seconds: int = 86_400
    ai_history_max_turns: int = 10

    # --- Ingress ---
    #: Set when `make tunnel` publishes the stack through Cloudflare, which is
    #: also why `dev_bypass_refusal` and `trusted_client_ip_header` read it.
    cloudflare_tunnel_token: str | None = None
    #: The header carrying the real client address, written by the one proxy in
    #: front of the API. IP rate limits bucket by it. Unset, and with no tunnel
    #: token, the TCP peer is the client.
    client_ip_header: str | None = None

    #: Public base URL of the customer PWA. Used to build `ticket_page_url`
    #: (docs/07 section 7) — a ticket the customer cannot open is not a ticket —
    #: and the only origin a payment's `return_url` may point at.
    public_app_url: str = "http://localhost:5173"

    # --- Business photos ---
    #: Where uploaded photos are kept (`integrations/storage`). A directory on a
    #: named volume in compose; any path the process may write to elsewhere.
    media_root: str = "/var/lib/nova/media"
    #: The largest upload accepted, before decoding. Phone photos run 3-6 MB.
    media_max_upload_bytes: int = 10 * 1024 * 1024

    #: Serve `/docs`, `/redoc` and `/openapi.json`. Unset, they are served only in
    #: local and test: published, the schema maps every route and parameter for
    #: whoever finds the host.
    api_docs_enabled: bool | None = None

    @property
    def serve_api_docs(self) -> bool:
        if self.api_docs_enabled is not None:
            return self.api_docs_enabled
        return self.env in DEVELOPMENT_ENVS

    @property
    def trusted_client_ip_header(self) -> str | None:
        """The header a rate limit may read the client address from, if any.

        `CF-Connecting-IP` whenever a tunnel token is set: Cloudflare writes it
        itself, replacing any value the client sent, and with every published
        port on loopback the tunnel is the only way in.
        """
        if self.client_ip_header:
            return self.client_ip_header
        return "CF-Connecting-IP" if self.cloudflare_tunnel_token else None

    @model_validator(mode="after")
    def _refuse_unsafe_configuration(self) -> "Settings":
        """Stops a process starting on settings that switch its security off.

        SECRET_KEY signs every token, slot id, QR ticket and upload
        authorisation, so anyone who can guess it can mint a service principal
        that reaches every tenant.
        """
        if not self.secret_key:
            raise ValueError("SECRET_KEY is empty. Generate one: openssl rand -hex 32")
        if self.env not in DEVELOPMENT_ENVS and (
            len(self.secret_key) < MIN_SECRET_KEY_LENGTH
            or self.secret_key.lower().startswith("change")
        ):
            raise ValueError(
                f"SECRET_KEY is too weak for ENV={self.env}: use at least "
                f"{MIN_SECRET_KEY_LENGTH} random characters (openssl rand -hex 32)."
            )
        if (self.client_ip_header or "").strip().lower() == "x-forwarded-for":
            raise ValueError(
                "CLIENT_IP_HEADER cannot be X-Forwarded-For: its first entry is whatever the "
                "client sent. Name the header your proxy writes itself, such as CF-Connecting-IP."
            )
        refusal = dev_bypass_refusal(self)
        if refusal is not None:
            raise ValueError(refusal)
        return self


def dev_bypass_refusal(settings: Settings) -> str | None:
    """Why AUTH_DEV_BYPASS may not be honoured with these settings, or None.

    The bypass makes a request with no token a service principal, which reaches
    every tenant. That is acceptable on a developer's own machine only: never in
    a deployed environment, and never on a stack a Cloudflare tunnel publishes.
    """
    if not settings.auth_dev_bypass:
        return None
    if settings.env not in DEVELOPMENT_ENVS:
        return (
            f"AUTH_DEV_BYPASS is enabled with ENV={settings.env}; "
            "it is honoured only in local or test."
        )
    if settings.cloudflare_tunnel_token:
        return (
            "AUTH_DEV_BYPASS is enabled while CLOUDFLARE_TUNNEL_TOKEN is set; "
            "the tunnel would publish an API that needs no token."
        )
    return None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
