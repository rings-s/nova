/**
 * payment — nova_backend/app/modules/payment/router.py
 *
 * Deposits, captures and refunds. The Moyasar webhook has no frontend
 * counterpart — it is server-to-server and never called from the browser.
 */
import { http, tenantPath } from './client.js';
import { newIdempotencyKey } from '../utils/idempotency.js';

/**
 * @typedef {'pending'|'processing'|'captured'|'failed'|'refunded'|'partially_refunded'|'cancelled'} PaymentStatus
 */

/**
 * @typedef {Object} Payment
 * @property {string} id
 * @property {string|null} booking_id
 * @property {string} amount
 * @property {string} currency
 * @property {PaymentStatus} status
 * @property {string} gateway
 * @property {string|null} gateway_payment_id
 * @property {boolean} webhook_verified
 * @property {string} refunded_amount
 * @property {string|null} failure_code
 * @property {string|null} captured_at
 * @property {string} created_at
 */

/**
 * @typedef {Object} PaymentIntent
 * @property {Payment} payment
 * @property {string|null} redirect_url Where to send the customer to pay.
 */

/**
 * Starts a payment. Idempotency-keyed automatically — a retried intent that
 * opens a second gateway payment is a customer charged twice.
 *
 * `amount`/`currency` are staff-only overrides: a customer must omit both and
 * let the booking's own price and the tenant's deposit policy decide.
 * @param {string} tenantId
 * @param {{ bookingId: string, returnUrl: string, metadata?: Record<string, string>|null,
 *   amount?: string|number|null, currency?: string|null, idempotencyKey?: string }} params
 * @returns {Promise<PaymentIntent>}
 */
export function createPaymentIntent(
	tenantId,
	{
		bookingId,
		returnUrl,
		metadata = null,
		amount = null,
		currency = null,
		idempotencyKey = newIdempotencyKey()
	}
) {
	return http.post(
		tenantPath(tenantId, '/payments/intents'),
		{ booking_id: bookingId, return_url: returnUrl, metadata, amount, currency },
		{ idempotencyKey }
	);
}

/** Visibility is inherited from the payment's booking. @returns {Promise<Payment>} */
export function getPayment(tenantId, paymentId) {
	return http.get(tenantPath(tenantId, `/payments/${paymentId}`));
}

/** @returns {Promise<{ items: Payment[], total: number }>} */
export function listPaymentsForBooking(tenantId, bookingId) {
	return http.get(tenantPath(tenantId, '/payments'), { query: { booking_id: bookingId } });
}

/**
 * Refunds a captured payment. Owners and managers only (`refund_payments`),
 * idempotency-keyed — a double-submitted refund is real money leaving twice.
 * @param {string} tenantId
 * @param {string} paymentId
 * @param {{ amount?: string|number|null, reason?: string|null, idempotencyKey?: string }} [params]
 *   Omit `amount` to refund everything still refundable.
 * @returns {Promise<Payment>}
 */
export function refundPayment(
	tenantId,
	paymentId,
	{ amount = null, reason = null, idempotencyKey = newIdempotencyKey() } = {}
) {
	return http.post(
		tenantPath(tenantId, `/payments/${paymentId}/refund`),
		{ amount, reason },
		{ idempotencyKey }
	);
}
