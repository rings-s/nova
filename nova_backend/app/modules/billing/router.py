"""billing · DELIVERY layer — HTTP.

Layer rule: schemas, service, dependencies. No business rules here.

Every route but the published price list is gated by role, read from this
tenant's `memberships` rather than from the token (`RequirePermission`).
Subscribing, changing plan and cancelling commit the business to what it pays
NOVA, so they are the owner's (`manage_subscription`). Invoices, commission
lines, payouts and the subscription's terms are the owner's and the manager's
(`view_financials`). A customer has no business anywhere near any of it.

There is deliberately no endpoint that creates a commission line or edits an
invoice — commission accrues from a domain event and an issued invoice is
immutable (docs/11 section 5). The only write paths are the ones an owner
genuinely owns: subscribe, change plan, cancel.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.pagination import PageParams
from app.core.schemas import Page
from app.core.security import require_staff
from app.core.throttling import write_rate_limit
from app.modules.billing.dependencies import get_billing_service
from app.modules.billing.domain import (
    CommissionLine,
    Invoice,
    Subscription,
    SubscriptionCheckout,
)
from app.modules.billing.schemas import (
    CancelSubscriptionRequest,
    ChangePlanRequest,
    CheckoutOut,
    CommissionExplanationOut,
    CommissionLineOut,
    CreateSubscriptionRequest,
    InvoiceOut,
    PayoutOut,
    PlanOut,
    StandingOut,
    StartCheckoutRequest,
    SubscriptionOut,
)
from app.modules.billing.service import BillingService
from app.modules.booking.domain import BookingSource
from app.modules.identity.dependencies import RequirePermission
from app.modules.identity.domain import StaffPermission
from app.modules.payment.schemas import PaymentFormConfigOut
from app.modules.payment.service import PaymentFormConfig

router = APIRouter(prefix="/tenants/{tenant_id}/billing", tags=["billing"])

_MANAGE_SUBSCRIPTION = Depends(RequirePermission(StaffPermission.MANAGE_SUBSCRIPTION))
_VIEW_FINANCIALS = Depends(RequirePermission(StaffPermission.VIEW_FINANCIALS))


def _subscription_out(subscription: Subscription) -> SubscriptionOut:
    # The chosen plan's price, also while it waits on its first payment.
    amount = subscription.chosen_monthly_amount()
    return SubscriptionOut(
        id=subscription.id,
        business_id=subscription.business_id,
        tier=subscription.tier,
        status=subscription.status,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        seats=subscription.seats,
        locations=subscription.locations,
        cancel_at_period_end=subscription.cancel_at_period_end,
        annual=subscription.annual,
        monthly_amount=amount.amount,
        currency=amount.currency,
        marketplace_listing_hidden=subscription.marketplace_listing_hidden,
        trial_ends_at=subscription.trial_ends_at,
        trial_ai_messages_left=(
            subscription.trial_ai_messages_left if subscription.trialing else None
        ),
        locked=subscription.locked_on(datetime.now(UTC).date()),
    )


def _checkout_out(
    checkout: SubscriptionCheckout,
    redirect_url: str | None = None,
    form: PaymentFormConfig | None = None,
) -> CheckoutOut:
    return CheckoutOut(
        id=checkout.id,
        business_id=checkout.business_id,
        tier=checkout.tier,
        annual=checkout.annual,
        status=checkout.status,
        net_amount=checkout.net.amount,
        vat_amount=checkout.vat.amount,
        total_amount=checkout.total.amount,
        currency=checkout.total.currency,
        covers_from=checkout.covers_from,
        covers_until=checkout.covers_until,
        paid_at=checkout.paid_at,
        redirect_url=redirect_url,
        checkout=PaymentFormConfigOut.model_validate(form) if form else None,
    )


def _invoice_out(tenant_id: UUID, invoice: Invoice) -> InvoiceOut:
    return InvoiceOut(
        id=invoice.id,
        business_id=invoice.business_id,
        period_start=invoice.period.period_start,
        period_end=invoice.period.period_end,
        status=invoice.status,
        subscription_amount=invoice.subscription_amount,
        commission_amount=invoice.commission_amount,
        processing_amount=invoice.processing_amount,
        vat_amount=invoice.vat_amount,
        total_amount=invoice.total_amount,
        currency=invoice.currency,
        issued_at=invoice.issued_at,
        due_at=invoice.due_at,
        paid_at=invoice.paid_at,
        # docs/11 section 6 declares this field; it points at the endpoint
        # below so every invoice total can be traced to the bookings behind it.
        lines_url=f"/api/v1/tenants/{tenant_id}/billing/invoices/{invoice.id}/lines",
    )


def _line_out(line: CommissionLine) -> CommissionLineOut:
    return CommissionLineOut(
        id=line.id,
        booking_id=line.booking_id,
        source=BookingSource(line.source),
        commission_class=line.commission_class,
        base_amount=line.base_amount.amount,
        rate_pct=line.rate_pct,
        amount=line.amount.amount,
        currency=line.amount.currency,
        reversed=line.reversed,
        status=line.status,
        is_reversal=line.is_reversal,
        accrued_at=line.accrued_at,
    )


# --- plans ----------------------------------------------------------------


@router.get("/plans", response_model=Page[PlanOut])
async def list_plans(
    tenant_id: UUID,
    service: BillingService = Depends(get_billing_service),
) -> Page[PlanOut]:
    """The published price list (docs/11 section 2).

    Readable by any authenticated caller on the tenant: a salon comparing plans
    should not need staff rights to see what they cost.
    """
    plans = service.plans()
    return Page(
        items=[PlanOut.model_validate(p, from_attributes=True) for p in plans], total=len(plans)
    )


# --- subscription ---------------------------------------------------------


@router.post(
    "/subscriptions",
    response_model=SubscriptionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE_SUBSCRIPTION, Depends(write_rate_limit)],
)
async def create_subscription(
    tenant_id: UUID,
    payload: CreateSubscriptionRequest,
    session: AsyncSession = Depends(get_db_session),
    service: BillingService = Depends(get_billing_service),
) -> SubscriptionOut:
    """Subscribes a business to a plan. Owners only (`manage_subscription`).

    One subscription per business: change it with `/plan` afterwards. Every plan
    starts `trialing` for a free week (`trial_ends_at`), with 10 AI messages.
    Pay for it any time with `POST /subscriptions/{business_id}/checkout`; a
    trial that ends unpaid locks the business (`locked`) until it is paid."""
    subscription = await service.subscribe(**payload.model_dump())
    await session.commit()
    return _subscription_out(subscription)


@router.get(
    "/subscriptions/{business_id}",
    response_model=SubscriptionOut,
    dependencies=[_VIEW_FINANCIALS],
)
async def get_subscription(
    tenant_id: UUID,
    business_id: UUID,
    service: BillingService = Depends(get_billing_service),
) -> SubscriptionOut:
    """Owners and managers only. This is commercial terms — plan, price, seat
    and location counts, and `marketplace_listing_hidden`, which says in effect
    "this salon is three weeks late paying". None of it is a customer's
    business, nor the front desk's.

    `GET /plans` stays open: the published price list is public by design.
    """
    return _subscription_out(await service.get_subscription(business_id))


@router.get(
    "/subscriptions/{business_id}/standing",
    response_model=StandingOut,
    dependencies=[Depends(require_staff)],
)
async def get_standing(
    tenant_id: UUID,
    business_id: UUID,
    service: BillingService = Depends(get_billing_service),
) -> StandingOut:
    """Whether the business may use NOVA today. Any staff member.

    No prices or amounts: just whether a plan was chosen, whether it is on its
    free week (and how many trial AI messages are left), and `locked`, which
    means the trial ended unpaid and only Billing works until it is paid."""
    found = await service.find_subscription(business_id)
    if found is None:
        return StandingOut(business_id=business_id, has_plan=False, locked=True)
    return StandingOut(
        business_id=business_id,
        has_plan=True,
        tier=found.tier,
        status=found.status,
        trialing=found.trialing,
        trial_ends_at=found.trial_ends_at,
        trial_ai_messages_left=found.trial_ai_messages_left if found.trialing else None,
        locked=found.locked_on(datetime.now(UTC).date()),
    )


@router.post(
    "/subscriptions/{business_id}/plan",
    response_model=SubscriptionOut,
    dependencies=[_MANAGE_SUBSCRIPTION, Depends(write_rate_limit)],
)
async def change_plan(
    tenant_id: UUID,
    business_id: UUID,
    payload: ChangePlanRequest,
    session: AsyncSession = Depends(get_db_session),
    service: BillingService = Depends(get_billing_service),
) -> SubscriptionOut:
    """Moves plan. A downgrade below current seats or locations is refused by
    the domain with a 409, naming what is in the way.

    During the trial, or while unpaid, the business pays for whichever plan it
    has chosen when it pays (`POST /subscriptions/{business_id}/checkout`); a
    paid plan moves now and is billed at the new price from the next invoice."""
    subscription = await service.change_plan(business_id, tier=payload.tier, annual=payload.annual)
    await session.commit()
    return _subscription_out(subscription)


@router.post(
    "/subscriptions/{business_id}/checkout",
    response_model=CheckoutOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_MANAGE_SUBSCRIPTION, Depends(write_rate_limit)],
)
async def start_checkout(
    tenant_id: UUID,
    business_id: UUID,
    payload: StartCheckoutRequest,
    session: AsyncSession = Depends(get_db_session),
    service: BillingService = Depends(get_billing_service),
) -> CheckoutOut:
    """Opens a Moyasar invoice for a plan waiting on payment. Owners only.

    With a publishable key configured, `checkout` holds the options for
    Moyasar's embedded Payment Form, paid on the web app's own page; otherwise
    send the owner's browser to `redirect_url`. It charges the plan's price plus
    15% VAT for the current month (a year for an annual plan). Moyasar sends
    them back to `return_url?checkout=<id>`; call
    `POST /checkouts/{checkout_id}/sync` from there. 409
    `subscription_not_awaiting_payment` if there is nothing to pay; 503
    `integration_not_configured` without Moyasar keys."""
    started = await service.start_checkout(business_id, return_url=payload.return_url)
    await session.commit()
    return _checkout_out(started.checkout, started.redirect_url, started.form)


@router.post(
    "/checkouts/{checkout_id}/sync",
    response_model=CheckoutOut,
    dependencies=[_MANAGE_SUBSCRIPTION, Depends(write_rate_limit)],
)
async def sync_checkout(
    tenant_id: UUID,
    checkout_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: BillingService = Depends(get_billing_service),
) -> CheckoutOut:
    """Asks Moyasar how a plan payment went, and activates the plan if it was
    paid. Owners only. Called by the page Moyasar sends the owner back to; the
    redirect itself proves nothing, so this checks Moyasar's own record of the
    payment (amount, currency and checkout). Safe to call again."""
    checkout = await service.sync_checkout(checkout_id)
    await session.commit()
    return _checkout_out(checkout)


@router.post(
    "/subscriptions/{business_id}/cancel",
    response_model=SubscriptionOut,
    dependencies=[_MANAGE_SUBSCRIPTION, Depends(write_rate_limit)],
)
async def cancel_subscription(
    tenant_id: UUID,
    business_id: UUID,
    payload: CancelSubscriptionRequest,
    session: AsyncSession = Depends(get_db_session),
    service: BillingService = Depends(get_billing_service),
) -> SubscriptionOut:
    """Cancels a business's subscription. Owners only.

    By default it runs to the end of the period already paid for
    (`at_period_end: true`); send `false` to end it now."""
    subscription = await service.cancel_subscription(
        business_id, at_period_end=payload.at_period_end
    )
    await session.commit()
    return _subscription_out(subscription)


# --- invoices -------------------------------------------------------------


@router.get(
    "/invoices",
    response_model=Page[InvoiceOut],
    dependencies=[_VIEW_FINANCIALS],
)
async def list_invoices(
    tenant_id: UUID,
    business_id: UUID,
    params: PageParams = Depends(),
    service: BillingService = Depends(get_billing_service),
) -> Page[InvoiceOut]:
    """A business's monthly invoices from NOVA, newest first. Owners and managers."""
    invoices = await service.list_invoices(business_id, limit=params.limit, offset=params.offset)
    return Page(items=[_invoice_out(tenant_id, inv) for inv in invoices])


@router.get(
    "/invoices/{invoice_id}",
    response_model=InvoiceOut,
    dependencies=[_VIEW_FINANCIALS],
)
async def get_invoice(
    tenant_id: UUID,
    invoice_id: UUID,
    service: BillingService = Depends(get_billing_service),
) -> InvoiceOut:
    """One invoice. Owners and managers.

    `GET /billing/invoices/{invoice_id}/lines` lists the commission lines behind
    its total."""
    return _invoice_out(tenant_id, await service.get_invoice(invoice_id))


@router.get(
    "/invoices/{invoice_id}/lines",
    response_model=Page[CommissionLineOut],
    dependencies=[_VIEW_FINANCIALS],
)
async def list_invoice_lines(
    tenant_id: UUID,
    invoice_id: UUID,
    service: BillingService = Depends(get_billing_service),
) -> Page[CommissionLineOut]:
    """Every line behind an invoice total.

    docs/11's goal list: "Make every invoice line traceable to one booking."
    Each row here carries its `booking_id`, so a disputed charge resolves to an
    appointment rather than to an argument.
    """
    lines = await service.invoice_lines(invoice_id)
    return Page(items=[_line_out(line) for line in lines], total=len(lines))


@router.get(
    "/commission-lines/{line_id}/explain",
    response_model=CommissionExplanationOut,
    dependencies=[_VIEW_FINANCIALS],
)
async def explain_commission_line(
    tenant_id: UUID,
    line_id: UUID,
    service: BillingService = Depends(get_billing_service),
) -> CommissionExplanationOut:
    """Why this line cost what it cost, in words a salon owner can read."""
    return CommissionExplanationOut.model_validate(await service.explain_commission_line(line_id))


# --- payouts --------------------------------------------------------------


@router.get(
    "/payouts",
    response_model=Page[PayoutOut],
    dependencies=[_VIEW_FINANCIALS],
)
async def list_payouts(
    tenant_id: UUID,
    business_id: UUID,
    params: PageParams = Depends(),
    service: BillingService = Depends(get_billing_service),
) -> Page[PayoutOut]:
    """Daily settlements (docs/11 section 8), newest first."""
    rows = await service.list_payouts(business_id, limit=params.limit, offset=params.offset)
    return Page(items=[PayoutOut.model_validate(r) for r in rows])
