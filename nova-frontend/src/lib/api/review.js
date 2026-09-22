/**
 * review — nova_backend/app/modules/review/router.py
 *
 * Verified ratings: a customer rates one of their own completed visits, once.
 * The rating feeds the business's public score (`rating_average` /
 * `rating_count` on discovery results); the comment is visible to the
 * business's staff only.
 */
import { http, tenantPath } from './client.js';

/**
 * @typedef {Object} MyReview
 * @property {string} id
 * @property {string} booking_id
 * @property {string} business_id
 * @property {number} rating 1–5
 * @property {string|null} comment
 * @property {string} created_at
 */

/**
 * @typedef {MyReview & { location_id: string, provider_id: string, customer_id: string }} Review
 */

/**
 * Rate a completed visit. 409 `already_reviewed` if it was rated before,
 * 409 `review_not_allowed` if the visit has not been completed.
 * @param {string} tenantId
 * @param {{ bookingId: string, rating: number, comment?: string|null }} params
 * @returns {Promise<MyReview>}
 */
export function submitReview(tenantId, { bookingId, rating, comment = null }) {
	return http.post(tenantPath(tenantId, '/reviews'), {
		booking_id: bookingId,
		rating,
		comment
	});
}

/**
 * The caller's own reviews at this tenant — which visits they have rated.
 * @param {string} tenantId @returns {Promise<MyReview[]>}
 */
export function listMyReviews(tenantId) {
	return http.get(tenantPath(tenantId, '/reviews/mine'));
}

/**
 * Staff: every review of one business, newest first, comments included.
 * @param {string} tenantId @param {string} businessId
 * @param {{ limit?: number, offset?: number }} [params]
 * @returns {Promise<{ items: Review[] }>}
 */
export function listBusinessReviews(tenantId, businessId, { limit = 20, offset = 0 } = {}) {
	return http.get(tenantPath(tenantId, '/reviews'), {
		query: { business_id: businessId, limit, offset }
	});
}
