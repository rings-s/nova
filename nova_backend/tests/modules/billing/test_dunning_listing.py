"""Day 21 of an unpaid invoice takes the salon off the marketplace (docs/11
section 8), and payment puts it back. Needs Postgres.

Billing decides; catalog owns the listing; the worker carries one to the other
(`on_invoice_standing_changed`). Before that handler existed the decision was
recorded on the subscription and nothing read it.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import set_tenant_scope
from app.modules.billing.dependencies import build_billing_service
from app.worker.handlers import handlers_for, on_invoice_standing_changed

DISCOVERY = "/api/v1/discovery"


def _event(business) -> dict[str, str]:
    return {"business_id": str(business.id)}


async def _subscribe(db_session: AsyncSession, business, *, hidden: bool):
    billing = build_billing_service(db_session, business.tenant_id)
    subscription = await billing.subscribe(business_id=business.id)
    if hidden:
        subscription.hide_marketplace_listing()
    else:
        subscription.activate()
    await billing.subscriptions.save(subscription)
    return subscription


def test_both_invoice_events_reach_the_listing() -> None:
    assert on_invoice_standing_changed in handlers_for("InvoiceOverdue")
    assert on_invoice_standing_changed in handlers_for("InvoicePaid")


async def test_a_business_hidden_by_billing_is_not_on_the_marketplace(
    client, tenant_factory, business_factory, location_factory, db_session, as_owner
):
    """As the schema owner, not under a tenant scope: a scope set in this
    transaction would let the discovery request see the salon through
    `tenant_isolation` rather than be refused it by the public predicate."""
    business = await business_factory(
        await tenant_factory(), name_en="Overdue Salon", slug="overdue-salon"
    )
    await location_factory(business)
    async with as_owner():
        business.hidden_by_billing = True
        await db_session.flush()

    search = await client.get(DISCOVERY + "/businesses", params={"q": "Overdue"})
    assert search.json()["items"] == []
    assert (await client.get(f"{DISCOVERY}/businesses/overdue-salon")).status_code == 404


async def test_day_twenty_one_hides_the_listing(tenant_factory, business_factory, db_session):
    business = await business_factory(await tenant_factory())
    await set_tenant_scope(db_session, business.tenant_id)
    await _subscribe(db_session, business, hidden=True)

    await on_invoice_standing_changed(db_session, business.tenant_id, _event(business))

    await db_session.refresh(business)
    assert business.hidden_by_billing is True
    assert business.is_listed is True, "the owner's own switch is not billing's"


async def test_payment_restores_the_listing(tenant_factory, business_factory, db_session):
    business = await business_factory(await tenant_factory())
    await set_tenant_scope(db_session, business.tenant_id)
    subscription = await _subscribe(db_session, business, hidden=True)
    await on_invoice_standing_changed(db_session, business.tenant_id, _event(business))

    subscription.activate()
    await build_billing_service(db_session, business.tenant_id).subscriptions.save(subscription)
    await on_invoice_standing_changed(db_session, business.tenant_id, _event(business))

    await db_session.refresh(business)
    assert business.hidden_by_billing is False


async def test_payment_does_not_list_a_business_its_owner_hid(
    tenant_factory, business_factory, db_session
):
    business = await business_factory(await tenant_factory(), is_listed=False)
    await set_tenant_scope(db_session, business.tenant_id)
    await _subscribe(db_session, business, hidden=False)

    await on_invoice_standing_changed(db_session, business.tenant_id, _event(business))

    await db_session.refresh(business)
    assert business.is_listed is False


async def test_a_stale_overdue_event_after_payment_leaves_the_listing_up(
    tenant_factory, business_factory, db_session
):
    """At-least-once delivery: the overdue event can arrive after the invoice
    was paid. The handler reads the subscription as it is now."""
    business = await business_factory(await tenant_factory())
    await set_tenant_scope(db_session, business.tenant_id)
    await _subscribe(db_session, business, hidden=False)

    await on_invoice_standing_changed(db_session, business.tenant_id, _event(business))

    await db_session.refresh(business)
    assert business.hidden_by_billing is False


async def test_a_business_that_never_subscribed_stays_listed(
    tenant_factory, business_factory, db_session
):
    business = await business_factory(await tenant_factory())
    await set_tenant_scope(db_session, business.tenant_id)

    await on_invoice_standing_changed(db_session, business.tenant_id, _event(business))

    await db_session.refresh(business)
    assert business.hidden_by_billing is False
