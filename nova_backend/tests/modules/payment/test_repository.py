"""Persistence tests for payment. Needs Postgres.

`PaymentOut.created_at` (docs/07 section 8) is read from here, so it has to be
the row's own timestamp rather than whatever the entity was built with.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.values import Money
from app.db.session import set_tenant_scope
from app.modules.payment.domain import Payment, PaymentStatus
from app.modules.payment.repository import PaymentRepository

_LONG_AGO = datetime(2000, 1, 1, tzinfo=UTC)


def _payment(tenant_id: UUID) -> Payment:
    return Payment(
        id=uuid4(),
        tenant_id=tenant_id,
        booking_id=None,
        amount=Money(amount=Decimal("150.00"), currency="SAR"),
        status=PaymentStatus.PENDING,
        created_at=_LONG_AGO,
    )


async def test_a_stored_payment_reports_the_rows_created_at(
    db_session: AsyncSession, tenant_factory
) -> None:
    tenant = await tenant_factory()
    await set_tenant_scope(db_session, tenant.id)
    repository = PaymentRepository(db_session, tenant.id)

    stored = await repository.add_payment(_payment(tenant.id))
    fetched = await repository.get_payment(stored.id)

    assert stored.created_at != _LONG_AGO
    assert fetched is not None
    assert fetched.created_at == stored.created_at


async def test_repository_cannot_read_another_tenants_payment(
    db_session: AsyncSession, tenant_factory, as_owner
) -> None:
    tenant_a = await tenant_factory()
    tenant_b = await tenant_factory()
    payment = _payment(tenant_a.id)

    # As the owner, which RLS does not restrict, so the repository's own
    # filter is all that keeps tenant B out.
    async with as_owner():
        stored = await PaymentRepository(db_session, tenant_a.id).add_payment(payment)
        assert await PaymentRepository(db_session, tenant_b.id).get_payment(stored.id) is None
