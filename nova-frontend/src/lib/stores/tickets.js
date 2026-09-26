/**
 * The customer's QR tickets on this device, by booking id.
 *
 * The backend returns a ticket's `qr_payload` once, at issue, and keeps only a
 * hash of it; asking again *revokes* the old ticket and mints a new one. So a
 * ticket is kept here when it arrives (from the chat or from My bookings), and
 * reissued only when this device has none, or it has expired. Otherwise
 * opening My bookings would silently kill the QR already saved on the phone.
 *
 * It sits beside the session tokens in this browser's storage, and like them
 * is only as private as the device. Every access is guarded: storage can be
 * missing or blocked, and then a ticket is simply reissued.
 */

const STORAGE_KEY = 'nova.tickets.v1';

/**
 * @typedef {{ qr_payload: string, ticket_code: string, expires_at: string }} StoredTicket
 */

/** @returns {Record<string, StoredTicket>} */
function readAll() {
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		return raw ? JSON.parse(raw) : {};
	} catch {
		return {};
	}
}

/** @param {string} bookingId @returns {StoredTicket|null} */
export function savedTicket(bookingId) {
	const ticket = readAll()[bookingId];
	if (!ticket || new Date(ticket.expires_at).getTime() <= Date.now()) return null;
	return ticket;
}

/** @param {string} bookingId @param {StoredTicket} ticket */
export function saveTicket(bookingId, ticket) {
	const now = Date.now();
	// Drop expired ones while here, so the map does not grow forever.
	const all = Object.fromEntries(
		Object.entries(readAll()).filter(([, t]) => new Date(t.expires_at).getTime() > now)
	);
	all[bookingId] = {
		qr_payload: ticket.qr_payload,
		ticket_code: ticket.ticket_code,
		expires_at: ticket.expires_at
	};
	try {
		localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
	} catch {
		// Private mode or full storage: the ticket is still on screen.
	}
}
