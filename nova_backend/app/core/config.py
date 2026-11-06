from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: The environments where a developer convenience may relax a deployed rule.
DEVELOPMENT_ENVS = frozenset({"local", "test"})

#: The shortest SECRET_KEY a deployed environment accepts. `openssl rand -hex 32`
#: produces 64 characters.
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

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
    #: Cap on slots in one public availability response. The window bounds the
    #: date dimension; a salon with thirty stylists is the other one. Over it,
    #: whole days come off the end and the response says where to resume
    #: (`more_from`), so 1,500 fits two weeks for a salon of four or five.
    discovery_max_public_slots: int = 1500

    # --- Queue / tickets ---
    #: Virtual tickets expire this long after issue. An indefinitely valid QR
    #: code is a permanent bearer credential.
    ticket_ttl_hours: int = 12
    #: How far a walk-in yields to a booked appointment on the shared provider
    #: timeline. See `queue.domain.priority_key` for what this actually means.
    queue_walk_in_penalty_minutes: int = 15
    #: A queue entry still waiting (or called, or missed) this long after it
    #: joined is cancelled by the worker. The line is ordered by arrival, so a
    #: leftover from yesterday would otherwise be first in line tomorrow.
    queue_entry_max_age_hours: int = 14

    # --- Payments ---
    #: The account's *secret* key (`sk_test_…` or `sk_live_…`), from the
    #: Moyasar dashboard under Settings > API Keys. Unset, payments answer 503
    #: `integration_not_configured` and the rest of the app runs as normal.
    #: Read from MOYASAR_SECRET_KEY_ID, or MOYASAR_API_KEY.
    moyasar_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MOYASAR_SECRET_KEY_ID", "MOYASAR_API_KEY"),
    )
    #: The shared secret set on the webhook in the Moyasar dashboard (Settings >
    #: Webhooks). Moyasar sends it back as `secret_token` in every webhook body.
    moyasar_webhook_secret: str | None = None
    #: The account's *publishable* key (`pk_test_…` or `pk_live_…`), from the
    #: same dashboard page. It is public by design: the browser hands it to
    #: Moyasar's Payment Form, which can pay an invoice with it but can neither
    #: create one nor read a payment back. Unset, checkout falls back to
    #: Moyasar's hosted invoice page.
    moyasar_publishable_key: str | None = None
    moyasar_base_url: str = "https://api.moyasar.com/v1"
    #: How long a customer has to pay on Moyasar's checkout page before the
    #: invoice expires.
    moyasar_checkout_ttl_minutes: int = 30
    #: Deposit required to confirm a booking, as a percentage of service price.
    #: 0 means bookings confirm without payment (docs/11 allows both).
    default_deposit_percent: int = 0

    # --- Maps: reverse geocoding ---
    #: OpenStreetMap's Nominatim (ADR-0012), turning a branch's pin into its
    #: district and city. Its usage policy asks for an identifying User-Agent
    #: and at most one request a second; point this at your own instance for
    #: more. Empty switches the lookup off (503 `integration_not_configured`).
    geocoder_url: str = "https://nominatim.openstreetmap.org"
    geocoder_timeout_seconds: float = 8.0

    # --- Notifications / WhatsApp ---
    whatsapp_bsp_api_key: str | None = None
    whatsapp_bsp_base_url: str | None = None
    whatsapp_phone_number_id: str | None = None
    #: Local-time window during which non-urgent messages are held. GCC norms;
    #: see `notification.domain.is_within_quiet_hours`.
    quiet_hours_start: int = 22
    quiet_hours_end: int = 8

    # --- AI agents (docs/04, docs/10) ---
    #: The models come from vLLM only: the compose `llm` service (ADR-0019),
    #: in every environment. Nothing reads this; it is here so a stale
    #: `llamacpp`, `ollama`, `lmstudio` or `openai_compatible` value stops the
    #: process at startup instead of being silently ignored.
    ai_provider: Literal["vllm"] = "vllm"
    #: vLLM's OpenAI-compatible /v1 URL: the compose `llm` service by default.
    ai_base_url: str = "http://llm:8000/v1"
    #: Local servers ignore it; set it if the server is started with auth on.
    ai_api_key: str | None = None
    #: The `llm` service's `--served-model-name` (`LLM_ALIAS`). It must contain
    #: `qwen3` for thinking to be switched off. Qwen3-4B by default, on a GPU;
    #: a CPU-only machine serves Qwen3-1.7B instead (`infra/.env`).
    ai_routing_model: str = "qwen3-4b"
    ai_reasoning_model: str = "qwen3-4b"
    #: Let a hybrid reasoning model (Qwen3) think before it answers. Off by
    #: default: on a CPU or small GPU thinking multiplies a turn's time (about
    #: 5x for qwen3-8b) for little gain on these narrow tool tasks.
    ai_thinking: bool = False
    #: docs/10 section 12: abort the turn and hand off past this.
    ai_tool_timeout_seconds: float = 5.0
    ai_request_timeout_seconds: float = 30.0
    ai_enabled: bool = True
    #: Turns allowed to run at once in this process, and how long a further one
    #: waits for a slot before the caller is told to retry (`ai_busy`). Match the
    #: model server: the `llm` service with `LLM_PARALLEL=N` runs N sequences
    #: at a time. One, as `LLM_PARALLEL` defaults to: on a CPU, a second turn
    #: halves the speed of both and competes for the prefix cache.
    ai_max_concurrent_turns: int = 1
    ai_queue_wait_seconds: float = 15.0
    #: How long a conversation's recent turns are remembered, and how many
    #: (`ai_agents/history.py`). Working memory for the model, not a record.
    ai_history_ttl_seconds: int = 86_400
    ai_history_max_turns: int = 10

    # --- Sara, the call-center agent, on Unifonic Voice (ADR-0017) ---
    #: The Unifonic Voice API key, for placing outbound calls. Inbound calls need
    #: none: Unifonic calls the line's URL. Unset, reminder calls are skipped.
    unifonic_voice_api_key: str | None = None
    #: To verify against the Unifonic console's API reference before go-live.
    unifonic_voice_base_url: str = "https://voice.unifonic.com/v1"
    #: The API's public origin as Unifonic reaches it (`https://api.example.sa`),
    #: for the absolute URL each reply tells Unifonic to send the caller's answer
    #: to. Unset, an inbound call uses the origin its own request arrived on,
    #: and an outbound call is not placed.
    voice_public_base_url: str | None = None
    #: The model Sara thinks with: a vLLM server too, at its own URL if a
    #: faster one is run for her, since a phone call waits on every turn. Each
    #: unset value falls back to its `AI_*` setting; the provider is a guard
    #: like `ai_provider`.
    voice_ai_provider: Literal["vllm"] | None = None
    voice_ai_base_url: str | None = None
    voice_ai_api_key: str | None = None
    voice_ai_model: str | None = None
    #: Kept under Unifonic's wait for a reply, so a slow model costs the caller
    #: a "could you say that again" rather than a dropped call.
    voice_ai_request_timeout_seconds: float = 6.0
    voice_ai_tool_timeout_seconds: float = 3.0
    #: Sara's voice: an OpenAI-compatible `/audio/speech` server. NOVA's own is
    #: the compose `tts` service (`infra/tts`, ADR-0018, `http://tts:8091/v1`),
    #: serving the Saudi Qwen3-TTS fine-tune (`vadimbelsky/qwen3-TTS-KSA`).
    #: Unset, Unifonic's own text-to-speech reads her replies.
    voice_tts_base_url: str | None = None
    voice_tts_api_key: str | None = None
    voice_tts_model: str = "vadimbelsky/qwen3-TTS-KSA"
    voice_tts_voice: str = "ksa_speaker"
    #: Passed as Qwen3-TTS's `language`. The KSA fine-tune speaks Arabic only, so
    #: an English reply is read by Unifonic's voice instead.
    voice_tts_language: str = "Arabic"
    #: A style prompt (`instructions`), e.g. "Warm and friendly". Empty: none.
    voice_tts_instructions: str = ""
    #: A phone line carries 8 kHz audio; Qwen3-TTS makes 8000 or 24000 Hz.
    voice_tts_sample_rate: int = 8000
    #: Past this, the reply is read by Unifonic's voice rather than keep the
    #: caller waiting longer.
    voice_tts_timeout_seconds: float = 4.0
    #: The most a caller waits for one answer, from Unifonic's request to ours:
    #: the model's `VOICE_AI_REQUEST_TIMEOUT_SECONDS` and speech together. Speech
    #: gets whatever the model left (never more than `VOICE_TTS_TIMEOUT_SECONDS`);
    #: with too little left, Unifonic reads the text. Keep it under Unifonic's
    #: own wait for a reply, which is to verify on a live account.
    voice_turn_budget_seconds: float = Field(default=8.0, gt=0.0)
    #: How long a generated reply's audio is kept for Unifonic to fetch, and
    #: for the same words to be said again without generating them twice.
    voice_tts_cache_seconds: int = 3600
    #: Caller turns in one call before Sara says goodbye: a cap on what one call
    #: can cost, in model time and in the plan's AI messages.
    voice_max_turns_per_call: int = 30
    #: Speech Unifonic recognised with a lower `confidence` is asked for again
    #: instead of reaching the model. 0 trusts every transcript. Unifonic's
    #: scale is to verify on a live account: on a 0-100 scale this lets
    #: everything through, which fails safe.
    voice_min_speech_confidence: float = Field(default=0.3, ge=0.0)
    #: Reminder calls go out this far ahead of a confirmed booking, between
    #: these local hours, and at most this many a day per business.
    voice_reminder_hours_ahead: int = 24
    voice_call_window_start: int = 10
    voice_call_window_end: int = 21
    voice_reminder_daily_cap: int = 200
    #: After this many days a call keeps its outcome but not the caller's number
    #: or Sara's words (PDPL). The `scrub_old_calls` cron clears them nightly.
    voice_call_retention_days: int = Field(default=90, ge=1)

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
    #: Bearer token for GET /metrics. Unset, the endpoint answers 404 and the
    #: process exposes nothing: request volumes and outbox backlog are not public.
    metrics_token: str | None = None

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
        if self.env not in DEVELOPMENT_ENVS and self.trusted_client_ip_header is None:
            # Without one, every client is the proxy's address: IP rate limits
            # either bucket the world together or (with a trusting proxy-headers
            # setup) take the address the client wrote. docs/14 TM-02.
            raise ValueError(
                f"Set CLIENT_IP_HEADER (or CLOUDFLARE_TUNNEL_TOKEN) for ENV={self.env}: "
                "rate limits need the real client address, from a header your proxy writes."
            )
        if (self.client_ip_header or "").strip().lower() == "x-forwarded-for":
            raise ValueError(
                "CLIENT_IP_HEADER cannot be X-Forwarded-For: its first entry is whatever the "
                "client sent. Name the header your proxy writes itself, such as CF-Connecting-IP."
            )
        if self.moyasar_api_key and not self.moyasar_api_key.startswith(("sk_test_", "sk_live_")):
            # A publishable key can neither open a checkout nor read a payment
            # back, so every payment would fail at the first request.
            raise ValueError(
                "MOYASAR_API_KEY must be the account's secret key (sk_test_… or sk_live_…), "
                "not the publishable key (pk_…)."
            )
        if self.env == "production" and (self.moyasar_api_key or "").startswith("sk_test_"):
            raise ValueError(
                "MOYASAR_API_KEY is a test key in production: no payer would ever be charged."
            )
        if self.moyasar_publishable_key:
            if not self.moyasar_publishable_key.startswith(("pk_test_", "pk_live_")):
                raise ValueError(
                    "MOYASAR_PUBLISHABLE_KEY must be the account's publishable key "
                    "(pk_test_… or pk_live_…). Never put the secret key in it: it is sent "
                    "to every payer's browser."
                )
            if self.env == "production" and self.moyasar_publishable_key.startswith("pk_test_"):
                raise ValueError(
                    "MOYASAR_PUBLISHABLE_KEY is a test key in production: "
                    "no payer would ever be charged."
                )
            if self.moyasar_api_key and (
                self.moyasar_api_key.startswith("sk_test_")
                != self.moyasar_publishable_key.startswith("pk_test_")
            ):
                # A test invoice cannot be paid with a live form, nor the other
                # way round: every checkout would fail at Moyasar.
                raise ValueError(
                    "MOYASAR_API_KEY and MOYASAR_PUBLISHABLE_KEY must both be test keys "
                    "or both be live keys."
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
