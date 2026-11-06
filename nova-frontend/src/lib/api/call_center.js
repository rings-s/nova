/**
 * call_center — nova_backend/app/modules/call_center/router.py
 *
 * Sara, the AI agent who answers the business's phone (ADR-0017). Unifonic
 * carries the calls; the dashboard only reads the call log. Lines (the
 * numbers) are connected by a NOVA administrator.
 */
import { http, tenantPath } from './client.js';

/**
 * @typedef {'booked'|'queued'|'cancelled'|'callback_requested'|'reminder_kept'|'turn_limit'|'unavailable'|'no_answer'} CallOutcome
 */

/**
 * @typedef {Object} Call
 * @property {string} id
 * @property {string} line_id
 * @property {string} business_id
 * @property {'inbound'|'outbound'} direction
 * @property {'conversation'|'reminder'} purpose
 * @property {'in_progress'|'ended'} status
 * @property {CallOutcome|null} outcome
 * @property {string|null} caller_e164
 * @property {string|null} customer_id
 * @property {string|null} booking_id
 * @property {number} turns
 * @property {boolean} verified whether the caller typed the code sent to their WhatsApp
 * @property {string} started_at
 * @property {string|null} ended_at
 */

/**
 * The business's calls with Sara, newest first. Needs `view_customers`.
 * @param {string} tenantId
 * @param {{ limit?: number, offset?: number }} [params]
 * @returns {Promise<Call[]>}
 */
export function listCalls(tenantId, { limit = 50, offset = 0 } = {}) {
	return http.get(tenantPath(tenantId, '/call-center/calls'), { query: { limit, offset } });
}
