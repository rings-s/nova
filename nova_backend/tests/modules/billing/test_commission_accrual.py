"""Persisted first-booking commission, from completion through the worker handler."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import set_tenant_scope
from app.modules.billing.domain import CommissionClass, PlanTier, SubscriptionStatus
from app.modules.billing.models import (
    CommissionLineRecord,
    CustomerBusinessFirstBookingRecord,
    SubscriptionRecord,
)
from app.modules.booking.dependencies import build_booking_service
from app.modules.booking.domain import BookingSource, BookingStatus
from app.modules.booking.models import BookingRecord
from app.worker.handlers import on_booking_completed


def _booking(tenant_id, business_id, customer_id, *, source, starts_at):
    return BookingRecord(
        tenant_id=tenant_id,
        business_id=business_id,
        location_id=uuid4(),
        service_id=uuid4(),
        provider_id=uuid4(),
        customer_id=customer_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        price=Decimal("172.50"),
        currency="SAR",
        status=BookingStatus.IN_SERVICE,
        source=source,
    )


async def _complete_and_dispatch(db_session, tenant_id, booking):
    await build_booking_service(db_session, tenant_id).complete(booking.id)
    await on_booking_completed(db_session, tenant_id, {"booking_id": str(booking.id)})


@pytest.mark.parametrize(
    ("tier", "rate", "commission"),
    [
        (PlanTier.SOLO, Decimal("35.00"), Decimal("52.50")),
        (PlanTier.STUDIO, Decimal("30.00"), Decimal("45.00")),
        (PlanTier.CHAIN, Decimal("25.00"), Decimal("37.50")),
    ],
)
async def test_first_marketplace_booking_uses_plan_rate_and_repeat_is_free(
    db_session, tenant_factory, business_factory, customer_factory, tier, rate, commission
):
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    customer = await customer_factory(tenant)
    now = datetime.now(UTC)
    await set_tenant_scope(db_session, tenant.id)
    db_session.add(
        SubscriptionRecord(
            tenant_id=tenant.id,
            business_id=business.id,
            tier=tier,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=date.today(),
            current_period_end=date.today() + timedelta(days=30),
        )
    )
    first = _booking(
        tenant.id,
        business.id,
        customer.id,
        source=BookingSource.MARKETPLACE,
        starts_at=now + timedelta(days=1),
    )
    repeat = _booking(
        tenant.id,
        business.id,
        customer.id,
        source=BookingSource.MARKETPLACE,
        starts_at=now + timedelta(days=2),
    )
    db_session.add_all([first, repeat])
    await db_session.flush()

    await _complete_and_dispatch(db_session, tenant.id, first)
    await on_booking_completed(db_session, tenant.id, {"booking_id": str(first.id)})
    await _complete_and_dispatch(db_session, tenant.id, repeat)

    lines = (
        (
            await db_session.execute(
                select(CommissionLineRecord).order_by(CommissionLineRecord.booking_id)
            )
        )
        .scalars()
        .all()
    )
    by_booking = {line.booking_id: line for line in lines}
    first_line = by_booking[first.id]
    repeat_line = by_booking[repeat.id]

    assert len(lines) == 2
    assert first_line.commission_class is CommissionClass.NEW_MARKETPLACE
    assert first_line.base_amount == Decimal("150.00")
    assert first_line.rate_pct == rate
    assert first_line.amount == commission
    assert repeat_line.commission_class is CommissionClass.REPEAT
    assert repeat_line.rate_pct == Decimal("0")
    assert repeat_line.amount == Decimal("0.00")

    claim = (
        await db_session.execute(
            select(CustomerBusinessFirstBookingRecord).where(
                CustomerBusinessFirstBookingRecord.business_id == business.id,
                CustomerBusinessFirstBookingRecord.customer_id == customer.id,
            )
        )
    ).scalar_one()
    assert claim.booking_id == first.id
    assert claim.source == BookingSource.MARKETPLACE


async def test_direct_booking_is_free_and_does_not_claim_marketplace_introduction(
    db_session, tenant_factory, business_factory, customer_factory
):
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    customer = await customer_factory(tenant)
    await set_tenant_scope(db_session, tenant.id)
    direct = _booking(
        tenant.id,
        business.id,
        customer.id,
        source=BookingSource.DIRECT_LINK,
        starts_at=datetime.now(UTC) + timedelta(days=1),
    )
    marketplace = _booking(
        tenant.id,
        business.id,
        customer.id,
        source=BookingSource.MARKETPLACE,
        starts_at=datetime.now(UTC) + timedelta(days=2),
    )
    db_session.add_all([direct, marketplace])
    await db_session.flush()

    await _complete_and_dispatch(db_session, tenant.id, direct)
    await _complete_and_dispatch(db_session, tenant.id, marketplace)

    lines = (
        (
            await db_session.execute(
                select(CommissionLineRecord).where(
                    CommissionLineRecord.booking_id.in_([direct.id, marketplace.id])
                )
            )
        )
        .scalars()
        .all()
    )
    by_booking = {line.booking_id: line for line in lines}

    assert by_booking[direct.id].commission_class is CommissionClass.DIRECT
    assert by_booking[direct.id].amount == Decimal("0.00")
    assert by_booking[marketplace.id].commission_class is CommissionClass.NEW_MARKETPLACE
    assert by_booking[marketplace.id].amount == Decimal("52.50")
