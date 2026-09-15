/**
 * queue — nova_backend/app/modules/queue/router.py
 *
 * Walk-ins and QR check-in. There is deliberately no "set position" call:
 * ordering is derived server-side from arrival and appointment times.
 */
import { http, tenantPath } from './client.js';
import { newIdempotencyKey } from '../utils/idempotency.js';

/**
 * @typedef {'waiting'|'called'|'checked_in'|'in_service'|'completed'|'missed'|'cancelled'} QueueEntryStatus
 * @typedef {'walk_in'|'appointment'} QueueEntrySource
 * @typedef {'issued'|'redeemed'|'expired'|'revoked'} TicketStatus
 */

/**
 * @typedef {Object} Queue
 * @property {string} id
 * @property {string} tenant_id
 * @property {string} location_id
 * @property {string} name_en
 * @property {string} name_ar
 * @property {boolean} is_open
 * @property {number} average_service_minutes
 */

/**
 * @typedef {Object} QueueEntry
 * @property {string} id
 * @property {string} queue_id
 * @property {string} location_id
 * @property {string} customer_id
 * @property {string} service_id
 * @property {string|null} provider_id
 * @property {QueueEntryStatus} status
 * @property {QueueEntrySource} source
 * @property {number} position Monotonic join counter — audit only, never renumbered.
 * @property {number} party_size
 * @property {string|null} booking_id
 * @property {string|null} joined_at
 * @property {string|null} called_at
 * @property {number|null} place_in_line What the customer actually sees (1 = next).
 * @property {number|null} estimated_wait_minutes
 */

/**
 * @typedef {Object} Ticket
 * @property {string} id
 * @property {string} ticket_code
 * @property {string} qr_payload Returned exactly once, at issue.
 * @property {TicketStatus} status
 * @property {string} expires_at
 * @property {string} ticket_page_url
 */

/**
 * @typedef {Object} TicketState
 * @property {string} id
 * @property {string} ticket_code
 * @property {TicketStatus} status
 * @property {string} expires_at
 * @property {string|null} redeemed_at
 * @property {string|null} booking_id
 * @property {string|null} queue_entry_id
 */

/**
 * @typedef {Object} CheckInResult
 * @property {TicketState} ticket
 * @property {QueueEntry|null} entry
 */

// --- Queue administration (staff only) ---------------------------------------

/** @returns {Promise<Queue>} */
export function createQueue(
	tenantId,
	{ locationId, nameEn = 'Main Queue', nameAr = 'الطابور الرئيسي', averageServiceMinutes = 30 }
) {
	return http.post(tenantPath(tenantId, '/queues'), {
		location_id: locationId,
		name_en: nameEn,
		name_ar: nameAr,
		average_service_minutes: averageServiceMinutes
	});
}

/** @returns {Promise<{ items: Queue[] }>} */
export function listQueues(tenantId, locationId) {
	return http.get(tenantPath(tenantId, '/queues'), { query: { location_id: locationId } });
}

/** Closing a queue stops new joins; people already waiting are still served. @returns {Promise<Queue>} */
export function setQueueOpen(tenantId, queueId, isOpen) {
	return http.patch(tenantPath(tenantId, `/queues/${queueId}/open`), { is_open: isOpen });
}

// --- The line ------------------------------------------------------------

/**
 * Idempotency-keyed automatically, same reasoning as `createBooking`.
 * @param {string} tenantId
 * @param {string} queueId
 * @param {{ serviceId: string, providerId?: string|null, partySize?: number,
 *   bookingId?: string|null, onBehalfOfCustomerId?: string|null, idempotencyKey?: string }} params
 * @returns {Promise<QueueEntry>}
 */
export function joinQueue(
	tenantId,
	queueId,
	{
		serviceId,
		providerId = null,
		partySize = 1,
		bookingId = null,
		onBehalfOfCustomerId = null,
		idempotencyKey = newIdempotencyKey()
	}
) {
	return http.post(
		tenantPath(tenantId, `/queues/${queueId}/entries`),
		{
			service_id: serviceId,
			provider_id: providerId,
			party_size: partySize,
			booking_id: bookingId,
			on_behalf_of_customer_id: onBehalfOfCustomerId
		},
		{ idempotencyKey }
	);
}

/** The live line. Staff-only. @returns {Promise<{ items: QueueEntry[], total: number }>} */
export function listQueueEntries(tenantId, queueId, { limit = 50, offset = 0 } = {}) {
	return http.get(tenantPath(tenantId, `/queues/${queueId}/entries`), { query: { limit, offset } });
}

/** "How much longer?" — the caller's own entry only. @returns {Promise<QueueEntry>} */
export function getQueueEntry(tenantId, entryId) {
	return http.get(tenantPath(tenantId, `/queues/entries/${entryId}`));
}

/** @returns {Promise<QueueEntry>} */
export function callNext(tenantId, queueId, providerId = null) {
	return http.post(
		tenantPath(tenantId, `/queues/${queueId}/call-next`),
		undefined,
		providerId ? { query: { provider_id: providerId } } : undefined
	);
}

/** @returns {Promise<QueueEntry>} */
export function markMissed(tenantId, entryId) {
	return http.post(tenantPath(tenantId, `/queues/entries/${entryId}/missed`));
}

/** Someone who stepped outside and came back, rather than losing their place. @returns {Promise<QueueEntry>} */
export function requeue(tenantId, entryId) {
	return http.post(tenantPath(tenantId, `/queues/entries/${entryId}/requeue`));
}

/** @returns {Promise<QueueEntry>} */
export function startQueueService(tenantId, entryId) {
	return http.post(tenantPath(tenantId, `/queues/entries/${entryId}/start`));
}

/** @returns {Promise<QueueEntry>} */
export function completeQueueEntry(tenantId, entryId) {
	return http.post(tenantPath(tenantId, `/queues/entries/${entryId}/complete`));
}

/** A customer leaving the line themselves, or staff removing them. @returns {Promise<QueueEntry>} */
export function cancelQueueEntry(tenantId, entryId) {
	return http.post(tenantPath(tenantId, `/queues/entries/${entryId}/cancel`));
}

// --- Tickets -----------------------------------------------------------------

/**
 * Issues a QR ticket for the caller's own booking or queue entry.
 * @returns {Promise<Ticket>}
 */
export function issueTicket(tenantId, { bookingId = null, queueEntryId = null }) {
	return http.post(tenantPath(tenantId, '/tickets'), {
		booking_id: bookingId,
		queue_entry_id: queueEntryId
	});
}

/** Reception scans a QR ticket. Staff-only. @returns {Promise<CheckInResult>} */
export function checkInWithTicket(tenantId, qrPayload) {
	return http.post(tenantPath(tenantId, '/tickets/check-in'), { qr_payload: qrPayload });
}

/** @returns {Promise<TicketState>} */
export function revokeTicket(tenantId, ticketId) {
	return http.post(tenantPath(tenantId, `/tickets/${ticketId}/revoke`));
}
