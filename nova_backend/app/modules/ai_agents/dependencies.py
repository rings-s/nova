"""ai_agents · DELIVERY layer — DI providers, and the one place a session opens.

A chat turn holds no request transaction. Inference runs for seconds, and a
transaction open across it kept a pooled connection busy and held the advisory
locks `hold_slot` and `join_queue` take, so every other booking for that
provider waited on the model. Instead, `TenantServiceScope` opens a short unit
of work each time it is called — the checks before inference once, then every
tool call — scopes it to the tenant for RLS, builds the services on it with the
modules' own factories, and commits when the block completes.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from uuid import UUID

from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_authorized_tenant
from app.db.errors import translate_integrity_error
from app.db.session import get_session_factory, set_tenant_scope
from app.integrations.payments.moyasar import PaymentGateway
from app.modules.ai_agents.history import ConversationStore, RedisConversationStore
from app.modules.ai_agents.runtime import InferenceEngine, build_inference_engine
from app.modules.ai_agents.service import AiChatService, TenantServices
from app.modules.analytics.dependencies import build_analytics_service
from app.modules.billing.dependencies import build_billing_service
from app.modules.booking.dependencies import build_booking_service
from app.modules.catalog.dependencies import build_catalog_service
from app.modules.identity.dependencies import build_customer_service, build_membership_service
from app.modules.payment.dependencies import build_payment_service, get_payment_gateway
from app.modules.queue.dependencies import build_queue_service

#: Opens a transaction and yields its session: committed on a clean exit,
#: rolled back when the block raises.
Transaction = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@asynccontextmanager
async def _pooled_transaction() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session
        await session.commit()


def get_agent_transaction() -> Transaction:
    """A pooled connection per unit of work. Tests swap in a savepoint."""
    return _pooled_transaction


def _build_services(
    session: AsyncSession, tenant_id: UUID, *, gateway: PaymentGateway | None
) -> TenantServices:
    catalog = build_catalog_service(session, tenant_id)
    customers = build_customer_service(session, tenant_id)
    booking = build_booking_service(session, tenant_id, catalog=catalog, customers=customers)
    payment = build_payment_service(session, tenant_id, gateway=gateway, bookings=booking)
    queue = build_queue_service(
        session, tenant_id, catalog=catalog, customers=customers, bookings=booking
    )
    billing = build_billing_service(session, tenant_id)
    analytics = build_analytics_service(
        session,
        tenant_id,
        catalog=catalog,
        bookings=booking,
        payments=payment,
        queues=queue,
        billing=billing,
    )
    return TenantServices(
        booking=booking,
        queue=queue,
        catalog=catalog,
        payment=payment,
        billing=billing,
        analytics=analytics,
        memberships=build_membership_service(session, tenant_id),
    )


class TenantServiceScope:
    """`service.ServiceScope` over real transactions, for one tenant."""

    def __init__(
        self,
        tenant_id: UUID,
        *,
        transaction: Transaction,
        gateway: PaymentGateway | None = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._transaction = transaction
        self._gateway = gateway

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[TenantServices]:
        try:
            async with self._transaction() as session:
                await set_tenant_scope(session, self._tenant_id)
                yield _build_services(session, self._tenant_id, gateway=self._gateway)
        except IntegrityError as exc:
            # The translation the HTTP error handler applies, so a tool meets a
            # lost race as a refusal it can relay (`slot_unavailable`) rather
            # than an error that ends the turn.
            raise translate_integrity_error(exc) from exc


_conversation_store: ConversationStore | None = None


def get_conversation_store() -> ConversationStore:
    """One Redis client per process, as the rate limiter keeps. Tests use memory."""
    global _conversation_store
    if _conversation_store is None:
        settings = get_settings()
        _conversation_store = RedisConversationStore.from_url(
            str(settings.redis_url),
            ttl_seconds=settings.ai_history_ttl_seconds,
            max_turns=settings.ai_history_max_turns,
        )
    return _conversation_store


def get_inference_engine() -> InferenceEngine:
    return build_inference_engine(get_settings())


def get_ai_chat_service(
    tenant_id: UUID = Depends(get_authorized_tenant),
    engine: InferenceEngine = Depends(get_inference_engine),
    transaction: Transaction = Depends(get_agent_transaction),
    gateway: PaymentGateway = Depends(get_payment_gateway),
    history: ConversationStore = Depends(get_conversation_store),
) -> AiChatService:
    """Note what is NOT here: no request session, and no service built on one.

    The agent context owns no tables and reaches other modules only through
    their services, which is what makes it structurally incapable of bypassing
    a domain rule (docs/04, the golden rule). Those services live only as long
    as the unit of work that built them.
    """
    return AiChatService(
        engine=engine,
        services=TenantServiceScope(tenant_id, transaction=transaction, gateway=gateway),
        tenant_id=tenant_id,
        history=history,
    )
