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

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.pagination import PageParams
from app.core.schemas import Page
from app.core.throttling import write_rate_limit
from app.modules.billing.dependencies import get_billing_service
from app.modules.billing.domain import CommissionLine, Invoice, Subscription
from app.modules.billing.schemas import (
    CancelSubscriptionRequest,
    ChangePlanRequest,
    CommissionExplanationOut,
    CommissionLineOut,
    CreateSubscriptionRequest,
    InvoiceOut,
    PayoutOut,
    PlanOut,
    SubscriptionOut,
)
from app.modules.billing.service import BillingService
from app.modules.booking.domain import BookingSource
from app.modules.identity.dependencies import RequirePermission
from app.modules.identity.domain import StaffPermission

router = APIRouter(prefix="/tenants/{tenant_id}/billing", tags=["billing"])

_MANAGE_SUBSCRIPTION = Depends(RequirePermission(StaffPermission.MANAGE_SUBSCRIPTION))
_VIEW_FINANCIALS = Depends(RequirePermission(StaffPermission.VIEW_FINANCIALS))


def _subscription_out(subscription: Subscription) -> SubscriptionOut:
    amount = subscription.subscription_amount()
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
        monthly_amount=amount.amount,
        currency=amount.currency,
        marketplace_listing_hidden=subscription.marketplace_listing_hidden,
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
    the domain with a 409, naming what is in the way."""
    subscription = await service.change_plan(business_id, tier=payload.tier, annual=payload.annual)
    await session.commit()
    return _subscription_out(subscription)


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
