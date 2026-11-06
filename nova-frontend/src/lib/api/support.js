/**
 * support — nova_backend/app/modules/support/router.py
 *
 * Follow-ups: customers an AI agent (the chat assistants, or Sara on the
 * phone) promised a person would get back to. Every route needs
 * `view_customers`, because a follow-up holds the customer's contact and
 * their own words.
 */
import { http, tenantPath } from './client.js';

/**
 * @typedef {'escalated'|'agent_could_not_help'|'assistant_unavailable'|'code_not_sent'|'cancellation_failed'|'call_too_long'} FollowUpReason
 */

/**
 * @typedef {Object} FollowUp
 * @property {string} id
 * @property {'chat'|'call'} source
 * @property {FollowUpReason} reason
 * @property {'open'|'resolved'} status
 * @property {string|null} business_id
 * @property {string|null} customer_id null when the person has no customer record here yet
 * @property {string|null} booking_id
 * @property {string|null} contact_name
 * @property {string|null} contact_phone for a call, the number that called
 * @property {string|null} contact_email
 * @property {string|null} summary the agent's own summary of the problem
 * @property {string|null} customer_message the customer's last words before the handoff
 * @property {string} opened_at when it was opened, or last reopened
 * @property {string|null} resolved_at
 */

/**
 * Newest first. Leave `status` out for both open and resolved ones.
 * @param {string} tenantId
 * @param {{ status?: 'open'|'resolved', limit?: number, offset?: number }} [params]
 * @returns {Promise<{ items: FollowUp[] }>}
 */
export function listFollowUps(tenantId, { status, limit = 20, offset = 0 } = {}) {
	return http.get(tenantPath(tenantId, '/follow-ups'), { query: { status, limit, offset } });
}

/**
 * @param {string} tenantId
 * @returns {Promise<{ open: number }>}
 */
export function countFollowUps(tenantId) {
	return http.get(tenantPath(tenantId, '/follow-ups/count'));
}

/**
 * Marks it done once someone got back to the customer. It reopens by itself
 * if the same conversation or call hands off again.
 * @param {string} tenantId
 * @param {string} followUpId
 * @returns {Promise<FollowUp>}
 */
export function resolveFollowUp(tenantId, followUpId) {
	return http.post(tenantPath(tenantId, `/follow-ups/${followUpId}/resolve`));
}
