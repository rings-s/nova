"""billing · CONTRACT layer — API boundary DTOs.

Layer rule: pydantic only. Naming follows docs/07 section 1 and the shapes in
docs/11 section 6.

Every money field is `Decimal`, never float — the same rule the domain and the
database keep, held all the way to the JSON boundary.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.core.schemas import ApiSchema
from app.modules.billing.domain import (
    CheckoutStatus,
    CommissionClass,
    CommissionLineStatus,
    InvoiceStatus,
    PlanTier,
    SubscriptionStatus,
)
from app.modules.booking.domain import BookingSource
from app.modules.payment.schemas import PaymentFormConfigOut


class PlanOut(ApiSchema):
    """docs/11 section 6."""

    tier: PlanTier
    monthly_price: Decimal
    annual_price: Decimal | None
    currency: str = "SAR"
    new_client_commission_pct: Decimal
    repeat_commission_pct: Decimal = Decimal("0")
    processing_fee_pct: Decimal = Decimal("2.5")
    included_features: list[str] = []

    #: Not in docs/11 section 6, added because a client rendering the pricing
    #: table needs to know Chain's price is *per location* rather than flat.
    priced_per_location: bool = False
    max_seats: int | None = None
    max_locations: int | None = None
    #: None means unlimited.
    whatsapp_reminders_per_month: int | None = None
    #: 0 means month to month.
    contract_months: int = 0


class SubscriptionOut(ApiSchema):
    id: UUID
    business_id: UUID
    tier: PlanTier
    status: SubscriptionStatus
    current_period_start: date
    current_period_end: date
    seats: int
    locations: int
    cancel_at_period_end: bool
    #: Billed yearly. `monthly_amount` stays the per-month figure either way.
    annual: bool = False

    #: What the next invoice will charge for the subscription line, given the
    #: current footprint. A Chain with three branches pays 3 x 1,200.
    monthly_amount: Decimal
    currency: str = "SAR"
    #: docs/11 section 7 step 6, or a locked business: the marketplace listing
    #: is hidden for non-payment.
    marketplace_listing_hidden: bool = False
    #: The free week's last day is the day before this; set on every plan.
    trial_ends_at: date | None = None
    #: AI messages left in the trial; null once the plan is paid for.
    trial_ai_messages_left: int | None = None
    #: The trial ran out, or the plan is unpaid: nothing but Billing works.
    locked: bool = False


class StandingOut(ApiSchema):
    """Whether a business may use NOVA today, for every staff role: the
    dashboard reads it to decide whether to send everyone to Billing."""

    business_id: UUID
    #: False when the business has never chosen a plan.
    has_plan: bool
    tier: PlanTier | None = None
    status: SubscriptionStatus | None = None
    trialing: bool = False
    trial_ends_at: date | None = None
    trial_ai_messages_left: int | None = None
    locked: bool


class StartCheckoutRequest(ApiSchema):
    #: Where Moyasar sends the owner back, with `?checkout=<id>` added. Must be
    #: on the web app's own origin (`PUBLIC_APP_URL`).
    return_url: str = Field(max_length=2048)


class CheckoutOut(ApiSchema):
    id: UUID
    business_id: UUID
    tier: PlanTier
    annual: bool
    status: CheckoutStatus
    net_amount: Decimal
    vat_amount: Decimal
    total_amount: Decimal
    currency: str
    #: The months this payment covers: from `covers_from` up to, not
    #: including, `covers_until`.
    covers_from: date
    covers_until: date
    paid_at: datetime | None = None
    #: Moyasar's hosted page. Only when the checkout was just opened.
    redirect_url: str | None = None
    #: The embedded Payment Form's options, when a publishable key is set;
    #: the web app then pays in its own checkout page instead of redirecting.
    checkout: PaymentFormConfigOut | None = None


class CreateSubscriptionRequest(ApiSchema):
    business_id: UUID
    tier: PlanTier = PlanTier.SOLO
    seats: int = Field(default=1, ge=1)
    locations: int = Field(default=1, ge=1)
    annual: bool = False


class ChangePlanRequest(ApiSchema):
    tier: PlanTier
    annual: bool = False


class CancelSubscriptionRequest(ApiSchema):
    #: Default matches docs/11 section 5 — a cancelled subscription keeps read
    #: access until the end of the period already paid for.
    at_period_end: bool = True


class CommissionLineOut(ApiSchema):
    id: UUID
    booking_id: UUID
    source: BookingSource
    commission_class: CommissionClass
    base_amount: Decimal
    rate_pct: Decimal
    amount: Decimal
    currency: str = "SAR"
    reversed: bool = False
    status: CommissionLineStatus = CommissionLineStatus.DRAFT
    is_reversal: bool = False
    accrued_at: datetime


class InvoiceOut(ApiSchema):
    id: UUID
    business_id: UUID
    period_start: date
    period_end: date
    status: InvoiceStatus
    subscription_amount: Decimal
    commission_amount: Decimal
    processing_amount: Decimal
    vat_amount: Decimal
    total_amount: Decimal
    currency: str = "SAR"
    issued_at: datetime | None
    due_at: datetime | None
    paid_at: datetime | None = None
    lines_url: str


class PayoutOut(ApiSchema):
    """docs/11 section 8. `booking_ids` is what makes it reconcilable."""

    id: UUID
    business_id: UUID
    payout_date: date
    collected_amount: Decimal
    processing_fee: Decimal
    commission_netted: Decimal
    net_amount: Decimal
    currency: str = "SAR"
    booking_ids: list[UUID] = []
    paid_at: datetime | None = None


class CommissionExplanationOut(ApiSchema):
    """Why one line cost what it cost — the `billing_agent`'s read surface."""

    commission_class: str
    reason: str
    source: str
    base_amount: str
    rate_pct: str
    amount: str
    currency: str
    reversed: str
