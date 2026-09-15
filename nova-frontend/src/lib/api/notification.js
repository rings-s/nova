/**
 * notification — nova_backend/app/modules/notification/router.py
 *
 * A read-only delivery log. There is no "send" endpoint by design — messages
 * are triggered only by domain events, so consent and quiet-hours are never
 * bypassable from the client.
 */
import { http, tenantPath } from './client.js';

/**
 * @typedef {'whatsapp'|'sms'|'email'} NotificationChannel
 * @typedef {'booking_confirmation'|'booking_reminder'|'booking_cancelled'|'queue_called'|'payment_receipt'|'marketing_offer'} MessageTemplate
 * @typedef {'sent'|'delivered'|'failed'|'suppressed'|'scheduled'} NotificationStatus
 */

/**
 * @typedef {Object} Notification
 * @property {string} id
 * @property {string} customer_id
 * @property {NotificationChannel} channel
 * @property {MessageTemplate} template
 * @property {NotificationStatus} status
 * @property {string|null} scheduled_for Set when quiet hours held a marketing message back.
 * @property {string|null} sent_at
 * @property {string|null} error
 * @property {string} created_at
 */

/** The delivery log for one customer — "did they actually get told?". @returns {Promise<{ items: Notification[] }>} */
export function listCustomerNotifications(tenantId, customerId, { limit = 20, offset = 0 } = {}) {
	return http.get(tenantPath(tenantId, '/notifications'), {
		query: { customer_id: customerId, limit, offset }
	});
}
