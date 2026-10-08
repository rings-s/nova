/**
 * billing — nova_backend/app/modules/billing/router.py
 *
 * What a business pays NOVA. Every route but the published price list needs
 * a role permission (`manage_subscription` or `view_financials`), enforced
 * server-side from this tenant's membership — never trust the UI alone to
 * hide these, but it's still correct to hide them for roles that can't reach them.
 */
import { http, tenantPath } from './client.js';

/**
 * @typedef {'solo'|'studio'|'chain'} PlanTier
 * `trialing`: the plan's free week (every plan starts with one). `pending_payment`:
 * the week ended unpaid, and the business is locked until `startPlanCheckout` is paid.
 * @typedef {'trialing'|'pending_payment'|'active'|'past_due'|'cancelled'} SubscriptionStatus
 * @typedef {'draft'|'issued'|'paid'|'overdue'|'void'} InvoiceStatus
 * @typedef {'new_marketplace'|'repeat'|'direct'|'exempt'} CommissionClass
 * @typedef {'draft'|'accrued'|'invoiced'|'reversed'} CommissionLineStatus
 */

/**
 * @typedef {Object} Plan
 * @property {PlanTier} tier
 * @property {string} monthly_price
 * @property {string|null} annual_price
 * @property {string} currency
 * @property {string} new_client_commission_pct
 * @property {string} repeat_commission_pct
 * @property {string} processing_fee_pct
 * @property {string[]} included_features
 * @property {boolean} priced_per_location
 * @property {number|null} max_seats
 * @property {number|null} max_locations
 * @property {number|null} whatsapp_reminders_per_month Null means unlimited.
 * @property {number} contract_months 0 means month to month.
 */

/**
 * @typedef {Object} Subscription
 * @property {string} id
 * @property {string} business_id
 * @property {PlanTier} tier
 * @property {SubscriptionStatus} status
 * @property {string} current_period_start
 * @property {string} current_period_end
 * @property {number} seats
 * @property {number} locations
 * @property {boolean} cancel_at_period_end
 * @property {boolean} annual Billed yearly; `monthly_amount` is still per month.
 * @property {string} monthly_amount
 * @property {string} currency
 * @property {boolean} marketplace_listing_hidden The listing is hidden: 21+ days
 *   overdue, or the business is locked.
 * @property {string|null} [trial_ends_at] The free week's last day is the day before.
 * @property {number|null} [trial_ai_messages_left] Null once the plan is paid for.
 * @property {boolean} [locked] The trial ended unpaid: only Billing works.
 */

/**
 * Whether a business may use NOVA today; readable by every staff role.
 * @typedef {Object} Standing
 * @property {string} business_id
 * @property {boolean} has_plan
 * @property {PlanTier|null} tier
 * @property {SubscriptionStatus|null} status
 * @property {boolean} trialing
 * @property {string|null} trial_ends_at
 * @property {number|null} trial_ai_messages_left
 * @property {boolean} locked No plan, or a trial that ended unpaid.
 */

/**
 * @typedef {Object} Invoice
 * @property {string} id
 * @property {string} business_id
 * @property {string} period_start
 * @property {string} period_end
 * @property {InvoiceStatus} status
 * @property {string} subscription_amount
 * @property {string} commission_amount
 * @property {string} processing_amount
 * @property {string} vat_amount
 * @property {string} total_amount
 * @property {string} currency
 * @property {string|null} issued_at
 * @property {string|null} due_at
 * @property {string|null} paid_at
 * @property {string} lines_url
 */

/**
 * @typedef {Object} CommissionLine
 * @property {string} id
 * @property {string} booking_id
 * @property {import('./booking.js').BookingSource} source
 * @property {CommissionClass} commission_class
 * @property {string} base_amount
 * @property {string} rate_pct
 * @property {string} amount
 * @property {string} currency
 * @property {boolean} reversed
 * @property {CommissionLineStatus} status
 * @property {boolean} is_reversal
 * @property {string} accrued_at
 */

/**
 * @typedef {Object} Payout
 * @property {string} id
 * @property {string} business_id
 * @property {string} payout_date
 * @property {string} collected_amount
 * @property {string} processing_fee
 * @property {string} commission_netted
 * @property {string} net_amount
 * @property {string} currency
 * @property {string[]} booking_ids
 * @property {string|null} paid_at
 */

/**
 * @typedef {Object} CommissionExplanation
 * @property {string} commission_class
 * @property {string} reason
 * @property {string} source
 * @property {string} base_amount
 * @property {string} rate_pct
 * @property {string} amount
 * @property {string} currency
 * @property {string} reversed
 */

/**
 * The published price list. Open to any authenticated caller on the tenant.
 * @param {string} tenantId @returns {Promise<{ items: Plan[] }>}
 */
export function listPlans(tenantId) {
	return http.get(tenantPath(tenantId, '/billing/plans'));
}

/**
 * @param {string} tenantId
 * @param {{ businessId: string, tier?: PlanTier, seats?: number, locations?: number,
 *   annual?: boolean }} params
 * @returns {Promise<Subscription>}
 */
export function createSubscription(
	tenantId,
	{ businessId, tier = 'solo', seats = 1, locations = 1, annual = false }
) {
	return http.post(tenantPath(tenantId, '/billing/subscriptions'), {
		business_id: businessId,
		tier,
		seats,
		locations,
		annual
	});
}

/**
 * Whether the business is locked (no plan, or its trial ended unpaid), and how
 * its trial stands. Any staff member; the dashboard reads it on every load.
 * @param {string} tenantId @param {string} businessId @returns {Promise<Standing>}
 */
export function getStanding(tenantId, businessId) {
	return http.get(tenantPath(tenantId, `/billing/subscriptions/${businessId}/standing`));
}

/** @param {string} tenantId @param {string} businessId @returns {Promise<Subscription>} */
export function getSubscription(tenantId, businessId) {
	return http.get(tenantPath(tenantId, `/billing/subscriptions/${businessId}`));
}

/**
 * A downgrade below current seats or locations is refused with 409.
 * @param {string} tenantId @param {string} businessId
 * @param {{ tier: PlanTier, annual?: boolean }} params
 * @returns {Promise<Subscription>}
 */
export function changePlan(tenantId, businessId, { tier, annual = false }) {
	return http.post(tenantPath(tenantId, `/billing/subscriptions/${businessId}/plan`), {
		tier,
		annual
	});
}

/**
 * One payment for a paid plan: in NOVA's checkout page (`checkout`), else on
 * Moyasar's hosted page (`redirect_url`).
 * @typedef {Object} PlanCheckout
 * @property {string} id
 * @property {string} business_id
 * @property {PlanTier} tier
 * @property {boolean} annual
 * @property {'pending'|'paid'|'failed'} status
 * @property {string} net_amount
 * @property {string} vat_amount
 * @property {string} total_amount
 * @property {string} currency
 * @property {string} covers_from
 * @property {string} covers_until First day NOT covered.
 * @property {string|null} paid_at
 * @property {string|null} redirect_url Moyasar's page; only when just opened.
 * @property {import('./payment.js').PaymentFormConfig|null} [checkout] The embedded
 *   Payment Form's options, when the deployment has a publishable key; only when
 *   just opened. The way to pay when set.
 */

/**
 * Opens a Moyasar invoice for a plan waiting on payment (owner only): pay it in
 * the embedded form (`checkout`), else on Moyasar's page (`redirect_url`).
 * Moyasar sends the owner back to `returnUrl?checkout=<id>`; call
 * `syncPlanCheckout` from there. 503 `integration_not_configured` without keys.
 * @param {string} tenantId @param {string} businessId @param {string} returnUrl
 * @returns {Promise<PlanCheckout>}
 */
export function startPlanCheckout(tenantId, businessId, returnUrl) {
	return http.post(tenantPath(tenantId, `/billing/subscriptions/${businessId}/checkout`), {
		return_url: returnUrl
	});
}

/**
 * Asks Moyasar how the payment went and activates the plan if it was paid.
 * Safe to call again.
 * @param {string} tenantId @param {string} checkoutId @returns {Promise<PlanCheckout>}
 */
export function syncPlanCheckout(tenantId, checkoutId) {
	return http.post(tenantPath(tenantId, `/billing/checkouts/${checkoutId}/sync`));
}

/** @param {string} tenantId @param {string} businessId @param {boolean} [atPeriodEnd] @returns {Promise<Subscription>} */
export function cancelSubscription(tenantId, businessId, atPeriodEnd = true) {
	return http.post(tenantPath(tenantId, `/billing/subscriptions/${businessId}/cancel`), {
		at_period_end: atPeriodEnd
	});
}

/**
 * @param {string} tenantId @param {string} businessId
 * @param {{ limit?: number, offset?: number }} [params]
 * @returns {Promise<{ items: Invoice[] }>}
 */
export function listInvoices(tenantId, businessId, { limit = 20, offset = 0 } = {}) {
	return http.get(tenantPath(tenantId, '/billing/invoices'), {
		query: { business_id: businessId, limit, offset }
	});
}

/** @param {string} tenantId @param {string} invoiceId @returns {Promise<Invoice>} */
export function getInvoice(tenantId, invoiceId) {
	return http.get(tenantPath(tenantId, `/billing/invoices/${invoiceId}`));
}

/**
 * Every line behind an invoice total — each traceable to one booking.
 * @param {string} tenantId @param {string} invoiceId
 * @returns {Promise<{ items: CommissionLine[], total: number }>}
 */
export function listInvoiceLines(tenantId, invoiceId) {
	return http.get(tenantPath(tenantId, `/billing/invoices/${invoiceId}/lines`));
}

/**
 * Why one line cost what it cost, in words an owner can read.
 * @param {string} tenantId @param {string} lineId @returns {Promise<CommissionExplanation>}
 */
export function explainCommissionLine(tenantId, lineId) {
	return http.get(tenantPath(tenantId, `/billing/commission-lines/${lineId}/explain`));
}

/**
 * Daily settlements, newest first.
 * @param {string} tenantId @param {string} businessId
 * @param {{ limit?: number, offset?: number }} [params]
 * @returns {Promise<{ items: Payout[] }>}
 */
export function listPayouts(tenantId, businessId, { limit = 20, offset = 0 } = {}) {
	return http.get(tenantPath(tenantId, '/billing/payouts'), {
		query: { business_id: businessId, limit, offset }
	});
}
