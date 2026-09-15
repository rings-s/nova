/**
 * booking — nova_backend/app/modules/booking/router.py
 *
 * Availability, slot holds, the appointment lifecycle, and provider schedules.
 * `createBooking` and `joinQueue` (queue.js) are the two writes that take an
 * idempotency key — see `$lib/utils/idempotency.js`.
 */
import { http, tenantPath } from './client.js';
import { newIdempotencyKey } from '../utils/idempotency.js';

/**
 * @typedef {'draft'|'pending_payment'|'confirmed'|'checked_in'|'in_service'|'completed'|'cancelled'|'no_show'} BookingStatus
 * @typedef {'marketplace'|'direct_link'|'whatsapp'|'walk_in'|'reception'|'ai_agent'} BookingSource
 */

/**
 * @typedef {Object} Booking
 * @property {string} id
 * @property {string} tenant_id
 * @property {string} business_id
 * @property {string} location_id
 * @property {string} service_id
 * @property {string} provider_id
 * @property {string} customer_id
 * @property {string} starts_at
 * @property {string} ends_at
 * @property {string} price
 * @property {string} currency
 * @property {BookingStatus} status
 * @property {BookingSource} source
 * @property {string|null} cancellation_reason
 * @property {string|null} notes
 */

/**
 * @typedef {Object} AvailableSlot
 * @property {string} slot_id Signed — pass straight through to `createBooking`.
 * @property {string} provider_id
 * @property {string} location_id
 * @property {string} service_id
 * @property {string} starts_at
 * @property {string} ends_at
 * @property {number} remaining_capacity
 */

/**
 * @typedef {Object} SlotHold
 * @property {string} hold_token
 * @property {string} provider_id
 * @property {string} service_id
 * @property {string} starts_at
 * @property {string} ends_at
 * @property {string} expires_at
 */

/**
 * @typedef {Object} WorkingWindow
 * @property {number} weekday Monday = 0.
 * @property {number} start_minute
 * @property {number} end_minute
 */

/**
 * @typedef {Object} Schedule
 * @property {string} provider_id
 * @property {WorkingWindow[]} windows
 */

/**
 * @typedef {Object} ScheduleException
 * @property {string} id
 * @property {string} provider_id
 * @property {string} on_date
 * @property {boolean} is_closed
 * @property {number|null} start_minute
 * @property {number|null} end_minute
 * @property {string|null} reason
 */

// --- Availability & holds ---------------------------------------------------

/**
 * @param {string} tenantId
 * @param {{ providerId: string, serviceId: string, dateFrom: string, dateTo: string }} params
 * @returns {Promise<{ items: AvailableSlot[], total: number }>}
 */
export function getAvailability(tenantId, { providerId, serviceId, dateFrom, dateTo }) {
	return http.get(tenantPath(tenantId, '/bookings/availability'), {
		query: { provider_id: providerId, service_id: serviceId, date_from: dateFrom, date_to: dateTo }
	});
}

/**
 * Reserves a slot for a few minutes while checkout completes.
 * @param {string} tenantId
 * @param {{ providerId: string, serviceId: string, startsAt: string, slotId?: string|null }} params
 * @returns {Promise<SlotHold>}
 */
export function holdSlot(tenantId, { providerId, serviceId, startsAt, slotId = null }) {
	return http.post(tenantPath(tenantId, '/bookings/holds'), {
		provider_id: providerId,
		service_id: serviceId,
		starts_at: startsAt,
		slot_id: slotId
	});
}

/**
 * Abandoned checkout: give the slot back rather than waiting for expiry.
 * @param {string} tenantId @param {string} holdToken
 */
export function releaseSlotHold(tenantId, holdToken) {
	return http.delete(tenantPath(tenantId, `/bookings/holds/${holdToken}`));
}

// --- Schedules (staff only) --------------------------------------------------

/**
 * Replaces a provider's whole week.
 * @param {string} tenantId @param {string} providerId @param {WorkingWindow[]} windows
 * @returns {Promise<Schedule>}
 */
export function setProviderSchedule(tenantId, providerId, windows) {
	return http.put(tenantPath(tenantId, `/schedules/providers/${providerId}`), { windows });
}

/** @param {string} tenantId @param {string} providerId @returns {Promise<Schedule>} */
export function getProviderSchedule(tenantId, providerId) {
	return http.get(tenantPath(tenantId, `/schedules/providers/${providerId}`));
}

/**
 * Eid, a holiday, or one stylist's afternoon off.
 * @param {string} tenantId
 * @param {string} providerId
 * @param {{ onDate: string, isClosed?: boolean, startMinute?: number|null,
 *   endMinute?: number|null, reason?: string|null }} params
 * @returns {Promise<ScheduleException>}
 */
export function addScheduleException(
	tenantId,
	providerId,
	{ onDate, isClosed = true, startMinute = null, endMinute = null, reason = null }
) {
	return http.post(tenantPath(tenantId, `/schedules/providers/${providerId}/exceptions`), {
		on_date: onDate,
		is_closed: isClosed,
		start_minute: startMinute,
		end_minute: endMinute,
		reason
	});
}

// --- Bookings ----------------------------------------------------------------

/**
 * Creates a booking. Idempotency-keyed automatically — a customer on a flaky
 * connection tapping "Book" twice must not get two appointments.
 * @param {string} tenantId
 * @param {{ locationId: string, serviceId: string, providerId: string, startsAt: string,
 *   source?: BookingSource|null, notes?: string|null, holdToken?: string|null,
 *   slotId?: string|null, referralToken?: string|null, onBehalfOfCustomerId?: string|null,
 *   idempotencyKey?: string }} params
 * @returns {Promise<Booking>}
 */
export function createBooking(
	tenantId,
	{
		locationId,
		serviceId,
		providerId,
		startsAt,
		source = null,
		notes = null,
		holdToken = null,
		slotId = null,
		referralToken = null,
		onBehalfOfCustomerId = null,
		idempotencyKey = newIdempotencyKey()
	}
) {
	return http.post(
		tenantPath(tenantId, '/bookings'),
		{
			location_id: locationId,
			service_id: serviceId,
			provider_id: providerId,
			starts_at: startsAt,
			source,
			notes,
			hold_token: holdToken,
			slot_id: slotId,
			referral_token: referralToken,
			on_behalf_of_customer_id: onBehalfOfCustomerId
		},
		{ idempotencyKey }
	);
}

/**
 * Staff see any booking in their tenant; a customer sees only their own.
 * @param {string} tenantId @param {string} bookingId @returns {Promise<Booking>}
 */
export function getBooking(tenantId, bookingId) {
	return http.get(tenantPath(tenantId, `/bookings/${bookingId}`));
}

/**
 * @param {string} tenantId
 * @param {{ customerId?: string|null, limit?: number, offset?: number }} [params]
 *   `customerId` is staff-only — omit to get the authenticated customer's own bookings.
 * @returns {Promise<{ items: Booking[] }>}
 */
export function listBookings(tenantId, { customerId = null, limit = 20, offset = 0 } = {}) {
	return http.get(tenantPath(tenantId, '/bookings'), {
		query: { customer_id: customerId, limit, offset }
	});
}

/**
 * The day sheet for one provider. Staff-only.
 * @param {string} tenantId @param {string} providerId
 * @param {{ dateFrom: string, dateTo: string }} params
 * @returns {Promise<{ items: Booking[] }>}
 */
export function listProviderCalendar(tenantId, providerId, { dateFrom, dateTo }) {
	return http.get(tenantPath(tenantId, `/bookings/calendar/${providerId}`), {
		query: { date_from: dateFrom, date_to: dateTo }
	});
}

/**
 * Manual confirmation for a salon not taking deposits. Staff-only.
 * @param {string} tenantId @param {string} bookingId @returns {Promise<Booking>}
 */
export function confirmBooking(tenantId, bookingId) {
	return http.post(tenantPath(tenantId, `/bookings/${bookingId}/confirm`));
}

/**
 * @param {string} tenantId
 * @param {string} bookingId
 * @param {{ reason?: string|null, byStaff?: boolean }} [params] `byStaff` waives the
 *   cancellation deadline; the server re-checks the caller is actually staff.
 * @returns {Promise<Booking>}
 */
export function cancelBooking(tenantId, bookingId, { reason = null, byStaff = false } = {}) {
	return http.post(
		tenantPath(tenantId, `/bookings/${bookingId}/cancel`),
		{ reason },
		{ query: { by_staff: byStaff } }
	);
}

/**
 * Moves a booking, keeping its id.
 * @param {string} tenantId @param {string} bookingId
 * @param {{ newStartsAt: string, providerId?: string|null }} params
 * @returns {Promise<Booking>}
 */
export function rescheduleBooking(tenantId, bookingId, { newStartsAt, providerId = null }) {
	return http.post(tenantPath(tenantId, `/bookings/${bookingId}/reschedule`), {
		new_starts_at: newStartsAt,
		provider_id: providerId
	});
}

/** @param {string} tenantId @param {string} bookingId @returns {Promise<Booking>} */
export function checkInBooking(tenantId, bookingId) {
	return http.post(tenantPath(tenantId, `/bookings/${bookingId}/check-in`));
}

/** @param {string} tenantId @param {string} bookingId @returns {Promise<Booking>} */
export function startBookingService(tenantId, bookingId) {
	return http.post(tenantPath(tenantId, `/bookings/${bookingId}/start`));
}

/** @param {string} tenantId @param {string} bookingId @returns {Promise<Booking>} */
export function completeBooking(tenantId, bookingId) {
	return http.post(tenantPath(tenantId, `/bookings/${bookingId}/complete`));
}

/** @param {string} tenantId @param {string} bookingId @returns {Promise<Booking>} */
export function markBookingNoShow(tenantId, bookingId) {
	return http.post(tenantPath(tenantId, `/bookings/${bookingId}/no-show`));
}
