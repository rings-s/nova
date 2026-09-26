/**
 * identity · AUTH — nova_backend/app/modules/identity/auth_router.py
 *
 * Unauthenticated by design, so every call here passes `skipAuth: true`: none
 * of them should attach a stale bearer token, and none should trigger the
 * client's automatic refresh-on-401 (a bad login is a 401 that means "wrong
 * password", not "token expired").
 */
import { http } from './client.js';

/**
 * @typedef {Object} TokenPair
 * @property {string} access_token
 * @property {string|null} refresh_token Always null here: the web app signs in with
 *   `refresh_cookie`, so the refresh token is an httpOnly cookie no script can read.
 * @property {string} token_type
 * @property {number} expires_in Access token lifetime, in seconds.
 */

/**
 * @typedef {Object} RegisteredUser
 * @property {string} id
 * @property {string} email
 * @property {string} full_name
 * @property {boolean} [is_superuser] A NOVA administrator; only `me` says so.
 */

/**
 * @param {{ email: string, password: string, fullName: string, phone?: string|null }} params
 *   `password` needs at least 12 characters (RegisterRequest).
 * @returns {Promise<RegisteredUser>}
 */
export function register({ email, password, fullName, phone = null }) {
	return http.post(
		'/auth/register',
		{ email, password, full_name: fullName, phone },
		{ skipAuth: true }
	);
}

/**
 * @param {{ email: string, password: string }} params
 * @returns {Promise<TokenPair>}
 */
export function login({ email, password }) {
	return http.post('/auth/login', { email, password, refresh_cookie: true }, { skipAuth: true });
}

/**
 * A new token pair, from the refresh cookie `login` set. The new refresh token
 * replaces the cookie; it is never returned.
 * @returns {Promise<TokenPair>}
 */
export function refresh() {
	return http.post('/auth/refresh', {}, { skipAuth: true });
}

/** Deletes this browser's refresh cookie, which only the server can. */
export function logout() {
	return http.post('/auth/logout', undefined, { skipAuth: true });
}

/** Revokes every outstanding access/refresh token for the caller. */
export function logoutEverywhere() {
	return http.post('/auth/logout-everywhere');
}

/** Sends a short-lived, signed verification link to the account's own phone over WhatsApp. */
export function requestPhoneVerification() {
	return http.post('/auth/phone/verify/request');
}

/** @param {string} token The token WhatsApp delivered, not a typed-in code. */
export function confirmPhoneVerification(token) {
	return http.post('/auth/phone/verify/confirm', { token });
}

/**
 * The signed-in account, and whether it is a NOVA administrator. That flag only
 * decides which pages to show; every admin route checks it for itself.
 * @returns {Promise<RegisteredUser>}
 */
export function me() {
	return http.get('/auth/me');
}
