"""call_center · DELIVERY layer — DI providers.

The webhooks have no principal and no tenant context: the tenant comes from
the path and is proved by the signed link (`CallCenterService`), so the
service is built by hand on the request's session once the router has scoped
it. Sara's chat service is built here too, on the voice engine.
"""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session, get_tenant_context
from app.integrations.payments.moyasar import PaymentGateway
from app.integrations.voice.speech import (
    AudioStore,
    RedisAudioStore,
    SpeechSynthesizer,
    build_speech_synthesizer,
)
from app.integrations.voice.unifonic import VoiceGateway, build_voice_gateway
from app.integrations.whatsapp.client import WhatsAppClient
from app.modules.ai_agents.concurrency import InferenceGate
from app.modules.ai_agents.dependencies import (
    TenantServiceScope,
    Transaction,
    get_agent_transaction,
    get_conversation_store,
    turn_gate,
)
from app.modules.ai_agents.history import ConversationStore
from app.modules.ai_agents.runtime import InferenceEngine, build_voice_inference_engine
from app.modules.ai_agents.service import AiChatService
from app.modules.billing.dependencies import build_billing_service
from app.modules.booking.dependencies import build_booking_service
from app.modules.call_center.repository import (
    PhoneLineRepository,
    UnscopedCallRepository,
    VoiceCallRepository,
)
from app.modules.call_center.service import CallCenterService, CallSweeper, SaraVoice
from app.modules.catalog.dependencies import build_catalog_service
from app.modules.identity.dependencies import build_customer_service
from app.modules.notification.dependencies import get_whatsapp_client
from app.modules.payment.dependencies import get_payment_gateway
from app.modules.support.dependencies import build_support_service


def get_voice_gateway() -> VoiceGateway:
    settings = get_settings()
    return build_voice_gateway(
        api_key=settings.unifonic_voice_api_key, base_url=settings.unifonic_voice_base_url
    )


_audio_store: AudioStore | None = None


def get_audio_store() -> AudioStore:
    """One Redis client per process for Sara's clips. Tests use memory."""
    global _audio_store
    if _audio_store is None:
        _audio_store = RedisAudioStore.from_url(str(get_settings().redis_url))
    return _audio_store


def get_speech_synthesizer() -> SpeechSynthesizer | None:
    """Sara's voice (`VOICE_TTS_*`), or None for Unifonic's own."""
    return build_speech_synthesizer(get_settings())


def build_sara_voice(
    synthesizer: SpeechSynthesizer | None = None, store: AudioStore | None = None
) -> SaraVoice:
    settings = get_settings()
    return SaraVoice(
        synthesizer if synthesizer is not None else get_speech_synthesizer(),
        store or get_audio_store(),
        secret_key=settings.secret_key,
        ttl_seconds=settings.voice_tts_cache_seconds,
    )


def get_sara_voice(
    synthesizer: Annotated[SpeechSynthesizer | None, Depends(get_speech_synthesizer)],
    store: Annotated[AudioStore, Depends(get_audio_store)],
) -> SaraVoice:
    return build_sara_voice(synthesizer, store)


def get_voice_inference_engine() -> InferenceEngine:
    """Sara's model. Tests override this with a scripted one."""
    return build_voice_inference_engine(get_settings())


#: How long a phone turn queues for the model behind other turns. The caller
#: hears silence meanwhile, and the whole turn has a few seconds
#: (`VOICE_TURN_BUDGET_SECONDS`): past this, Sara asks them to say it again.
VOICE_GATE_WAIT_SECONDS = 1.0


def get_voice_turn_gate() -> Callable[[], InferenceGate] | None:
    """The chat agents' turn limiter, whenever Sara thinks on their server.

    With `VOICE_AI_BASE_URL` unset (the default) she uses the `llm` service,
    which serves `LLM_PARALLEL` turns at once to every agent. Anyone can dial a
    line, so outside the shared limit a few calls at once would queue every
    chat assistant behind them. A server of her own needs no share of it.
    """
    settings = get_settings()
    if settings.voice_ai_base_url and settings.voice_ai_base_url != settings.ai_base_url:
        return None
    return turn_gate


def build_call_center_service(
    session: AsyncSession,
    tenant_id: UUID,
    gateway: VoiceGateway | None = None,
    whatsapp: WhatsAppClient | None = None,
    chat: AiChatService | None = None,
    voice: SaraVoice | None = None,
) -> CallCenterService:
    """Assembles the service outside the request DI graph: webhooks and the worker."""
    settings = get_settings()
    catalog = build_catalog_service(session, tenant_id)
    customers = build_customer_service(session, tenant_id)
    return CallCenterService(
        session,
        tenant_id,
        lines=PhoneLineRepository(session, tenant_id),
        calls=VoiceCallRepository(session, tenant_id),
        customers=customers,
        bookings=build_booking_service(session, tenant_id, catalog=catalog, customers=customers),
        catalog=catalog,
        billing=build_billing_service(session, tenant_id),
        support=build_support_service(session, tenant_id, customers=customers),
        gateway=gateway or get_voice_gateway(),
        whatsapp=whatsapp or get_whatsapp_client(),
        secret_key=settings.secret_key,
        max_turns=settings.voice_max_turns_per_call,
        min_speech_confidence=settings.voice_min_speech_confidence,
        chat=chat,
        voice=voice or build_sara_voice(),
    )


def build_call_sweeper(session: AsyncSession) -> CallSweeper:
    """Cross-tenant, for the worker. Call `bypass_tenant_scope` on the session first."""
    return CallSweeper(UnscopedCallRepository(session))


class VoiceCallServices:
    """What a webhook needs to build the service once it knows the tenant.

    Collected by FastAPI, so tests swap the engine, transaction and memory as
    they do for the chat routes.
    """

    def __init__(
        self,
        engine: Annotated[InferenceEngine, Depends(get_voice_inference_engine)],
        transaction: Annotated[Transaction, Depends(get_agent_transaction)],
        payments: Annotated[PaymentGateway, Depends(get_payment_gateway)],
        history: Annotated[ConversationStore, Depends(get_conversation_store)],
        gateway: Annotated[VoiceGateway, Depends(get_voice_gateway)],
        whatsapp: Annotated[WhatsAppClient, Depends(get_whatsapp_client)],
        voice: Annotated[SaraVoice, Depends(get_sara_voice)],
        gate: Annotated[Callable[[], InferenceGate] | None, Depends(get_voice_turn_gate)],
    ) -> None:
        self.engine = engine
        self.transaction = transaction
        self.payments = payments
        self.history = history
        self.gateway = gateway
        self.whatsapp = whatsapp
        self.voice = voice
        self.gate = gate

    def build(self, session: AsyncSession, tenant_id: UUID) -> CallCenterService:
        chat = AiChatService(
            engine=self.engine,
            services=TenantServiceScope(
                tenant_id, transaction=self.transaction, gateway=self.payments
            ),
            tenant_id=tenant_id,
            history=self.history,
            gate_factory=self.gate,
            gate_wait_seconds=VOICE_GATE_WAIT_SECONDS,
        )
        return build_call_center_service(
            session,
            tenant_id,
            gateway=self.gateway,
            whatsapp=self.whatsapp,
            chat=chat,
            voice=self.voice,
        )


def get_call_center_service(
    tenant_id: Annotated[UUID, Depends(get_tenant_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    gateway: Annotated[VoiceGateway, Depends(get_voice_gateway)],
) -> CallCenterService:
    """For the staff and superuser routes, inside the request's tenant context."""
    return build_call_center_service(session, tenant_id, gateway=gateway)
