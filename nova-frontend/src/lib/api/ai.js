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
 * @property {string|null} required_feature
 */

/**
 * @typedef {Object} AgentCatalog
 * @property {string[]} available
 * @property {Record<string, string>} aliases Old agent names and what they resolve to.
 * @property {AgentInfo[]} agents
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
 */

/**
 * One turn of conversation.
 * @param {string} tenantId
 * @param {{ sessionId: string, message: string, channel?: string, locale?: string,
 *   customerId?: string|null, businessId?: string|null, agent?: string }} params
 *   `customerId` is staff-only, to ask on behalf of a named customer.
 *   `businessId` is required by the staff agents (accountant, analyst, business manager).
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
		agent = 'concierge_agent'
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
			business_id: businessId
		},
		{ query: { agent } }
	);
}

/**
 * The agent roster this deployment runs. Can legitimately answer "none that
 * work" when the optional AI extra or Ollama is offline — hide the chat entry
 * point rather than let a customer discover it only ever hands off.
 * @returns {Promise<AgentCatalog>}
 */
export function listAgents(tenantId) {
	return http.get(tenantPath(tenantId, '/ai/agents'));
}
