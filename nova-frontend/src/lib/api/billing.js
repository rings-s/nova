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
 * @typedef {'trialing'|'active'|'past_due'|'cancelled'} SubscriptionStatus
 * @typedef {'draft'|'issued'|'paid'|'overdue'|'void'} InvoiceStatus
 * @typedef {'new_marketplace'|'prepaid_online'} CommissionClass
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
 * @property {string} monthly_amount
 * @property {string} currency
 * @property {boolean} marketplace_listing_hidden True means 21+ days overdue: the
 *   listing is hidden, but the calendar, queue and existing bookings still work.
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

/** The published price list. Open to any authenticated caller on the tenant. @returns {Promise<{ items: Plan[] }>} */
export function listPlans(tenantId) {
	return http.get(tenantPath(tenantId, '/billing/plans'));
}

/** @returns {Promise<Subscription>} */
export function createSubscription(
	tenantId,
	{ businessId, tier = 'solo', seats = 1, locations = 1, annual = false, trialDays = 0 }
) {
	return http.post(tenantPath(tenantId, '/billing/subscriptions'), {
		business_id: businessId,
		tier,
		seats,
		locations,
		annual,
		trial_days: trialDays
	});
}

/** @returns {Promise<Subscription>} */
export function getSubscription(tenantId, businessId) {
	return http.get(tenantPath(tenantId, `/billing/subscriptions/${businessId}`));
}

/** A downgrade below current seats or locations is refused with 409. @returns {Promise<Subscription>} */
export function changePlan(tenantId, businessId, { tier, annual = false }) {
	return http.post(tenantPath(tenantId, `/billing/subscriptions/${businessId}/plan`), {
		tier,
		annual
	});
}

/** @returns {Promise<Subscription>} */
export function cancelSubscription(tenantId, businessId, atPeriodEnd = true) {
	return http.post(tenantPath(tenantId, `/billing/subscriptions/${businessId}/cancel`), {
		at_period_end: atPeriodEnd
	});
}

/** @returns {Promise<{ items: Invoice[] }>} */
export function listInvoices(tenantId, businessId, { limit = 20, offset = 0 } = {}) {
	return http.get(tenantPath(tenantId, '/billing/invoices'), {
		query: { business_id: businessId, limit, offset }
	});
}

/** @returns {Promise<Invoice>} */
export function getInvoice(tenantId, invoiceId) {
	return http.get(tenantPath(tenantId, `/billing/invoices/${invoiceId}`));
}

/** Every line behind an invoice total — each traceable to one booking. @returns {Promise<{ items: CommissionLine[], total: number }>} */
export function listInvoiceLines(tenantId, invoiceId) {
	return http.get(tenantPath(tenantId, `/billing/invoices/${invoiceId}/lines`));
}

/** Why one line cost what it cost, in words an owner can read. @returns {Promise<CommissionExplanation>} */
export function explainCommissionLine(tenantId, lineId) {
	return http.get(tenantPath(tenantId, `/billing/commission-lines/${lineId}/explain`));
}

/** Daily settlements, newest first. @returns {Promise<{ items: Payout[] }>} */
export function listPayouts(tenantId, businessId, { limit = 20, offset = 0 } = {}) {
	return http.get(tenantPath(tenantId, '/billing/payouts'), {
		query: { business_id: businessId, limit, offset }
	});
}
