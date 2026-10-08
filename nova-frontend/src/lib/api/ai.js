/**
 * ai_agents — nova_backend/app/modules/ai_agents/router.py
 *
 * PydanticAI agents as a chat turn. Every write a tool made is already
 * committed by the time a response comes back — `held_slots` and
 * `queue_places` are real even when `requires_human_handoff` is true. No
 * agent can confirm a booking or cancel one; `pending_cancellations` still
 * need the customer to call `cancelBooking` themselves.
 */
import { http, tenantPath } from './client.js';

/**
 * @typedef {Object} AgentInfo
 * @property {string} name
 * @property {string} audience
 * @property {string} goal
 * @property {string|null} required_feature Plan feature the business needs (`insights`).
 * @property {import('./identity.js').StaffPermission|null} required_permission Role permission a staff caller needs.
 * @property {boolean} needs_business Staff agents work on one business: send `businessId`.
 */

/**
 * @typedef {Object} AgentCatalog
 * @property {string[]} available
 * @property {Record<string, string>} aliases Old agent names and what they resolve to.
 * @property {AgentInfo[]} agents
 * @property {boolean} inference_available False when every turn would only hand off: the AI
 *   extra is missing, AI is disabled, or the local model server (LM Studio/Ollama) is not answering.
 */

/**
 * @typedef {Object} ProposedAction
 * @property {string} id
 * @property {string} kind
 * @property {string} title
 * @property {string} rationale
 * @property {string} metric
 * @property {string} target_type
 * @property {string|null} target_id
 * @property {string|null} apply_via Endpoint a person would call to apply it.
 * @property {boolean} requires_confirmation
 */

/**
 * @typedef {Object} QueuePlace
 * @property {string} entry_id
 * @property {string} queue_id
 * @property {number} place_in_line
 * @property {number|null} estimated_wait_minutes
 */

/**
 * @typedef {Object} PendingCancellation
 * @property {string} booking_id
 * @property {string} starts_at
 * @property {string|null} reason
 */

/**
 * @typedef {Object} AiChatResponse
 * @property {string} session_id
 * @property {string} agent The resolved agent name, even if you passed an old alias.
 * @property {string} reply
 * @property {string[]} suggested_actions
 * @property {boolean} requires_human_handoff
 * @property {string|null} related_booking_id
 * @property {string|null} related_ticket_url
 * @property {import('./booking.js').SlotHold[]} held_slots
 * @property {QueuePlace[]} queue_places
 * @property {PendingCancellation[]} pending_cancellations
 * @property {boolean} degraded True when a fallback model or static reply answered.
 * @property {number} confidence
 * @property {string[]} metrics_used
 * @property {import('./analytics.js').Chart[]} charts
 * @property {ProposedAction[]} proposed_actions
 * @property {BookingTicket[]} tickets Bookings an agent made this turn, with their QR tickets.
 */

/**
 * A booking an agent made, and the QR ticket the customer shows to check in.
 * `qr_payload` is the check-in credential: render it as a QR code, keep it out
 * of URLs and logs.
 * @typedef {Object} BookingTicket
 * @property {string} booking_id
 * @property {string} tenant_id
 * @property {string} business_name
 * @property {import('./booking.js').BookingStatus} booking_status
 * @property {string} starts_at
 * @property {string} ends_at
 * @property {string} ticket_id
 * @property {string} ticket_code
 * @property {string} qr_payload
 * @property {string} expires_at
 * @property {string} ticket_page_url
 */

/**
 * One turn of conversation.
 * @param {string} tenantId
 * @param {{ sessionId: string, message: string, channel?: string, locale?: string,
 *   customerId?: string|null, businessId?: string|null, agent?: string,
 *   referralToken?: string|null, confirmHoldToken?: string|null }} params
 *   `customerId` is staff-only, to ask on behalf of a named customer.
 *   `businessId` is required by the staff agents (accountant, analyst, business manager);
 *   the receptionist takes it as the storefront the customer is on.
 *   `referralToken` is the storefront visit's, so an agent's booking is attributed the same way.
 *   `confirmHoldToken` is the held slot the customer pressed "Yes, book it" on; the agent books
 *   only that one, never on a "yes" typed in words.
 * @returns {Promise<AiChatResponse>}
 */
export function sendChatMessage(
	tenantId,
	{
		sessionId,
		message,
		channel = 'pwa',
		locale = 'ar',
		customerId = null,
		businessId = null,
		agent = 'concierge_agent',
		referralToken = null,
		confirmHoldToken = null
	}
) {
	return http.post(
		tenantPath(tenantId, '/ai/chat'),
		{
			session_id: sessionId,
			message,
			channel,
			locale,
			customer_id: customerId,
			business_id: businessId,
			referral_token: referralToken,
			confirm_hold_token: confirmHoldToken
		},
		{ query: { agent } }
	);
}

/**
 * The agent roster this deployment runs. `inference_available` is false when
 * the optional AI extra or the local model server is offline — hide the chat
 * entry point rather than let a customer discover it only ever hands off.
 * @param {string} tenantId @returns {Promise<AgentCatalog>}
 */
export function listAgents(tenantId) {
	return http.get(tenantPath(tenantId, '/ai/agents'));
}

/**
 * One turn with the marketplace assistant: it searches every listed business,
 * holds a time and books it once the customer presses its "Yes, book it"
 * (`confirmHoldToken`). Signed-in customers only.
 * @param {{ sessionId: string, message: string, channel?: string, locale?: string,
 *   confirmHoldToken?: string|null }} params
 * @returns {Promise<AiChatResponse>}
 */
export function sendMarketplaceMessage({
	sessionId,
	message,
	channel = 'pwa',
	locale = 'ar',
	confirmHoldToken = null
}) {
	return http.post('/discovery/ai/chat', {
		session_id: sessionId,
		message,
		channel,
		locale,
		confirm_hold_token: confirmHoldToken
	});
}

/**
 * Whether the marketplace assistant can answer right now.
 * @returns {Promise<{ inference_available: boolean }>}
 */
export function getMarketplaceAssistant() {
	return http.get('/discovery/ai/status');
}

/**
 * Forgets every AI conversation the caller has had, at any business and on the
 * marketplace: the remembered turns, and the offered times kept with them (an
 * earlier offer can no longer be booked). Bookings and tickets are untouched.
 * Fails with `ai_memory_unavailable` rather than claiming success when the
 * server cannot reach its memory.
 * @returns {Promise<{ forgotten: number }>}
 */
export function forgetMyConversations() {
	return http.delete('/ai/conversations');
}
