import { t, i18n } from '$lib/i18n/index.svelte.js';
/**
 * Turns a thrown value — an `ApiError`, a `NetworkError`, or anything else —
 * into text a form or toast can show. Centralised so every `catch` block
 * reads the same way instead of reaching into `err.message` under `unknown`.
 */
import { ApiError, NetworkError } from '../api/client.js';
import { AR } from '../i18n/ar.js';

/**
 * In Arabic, a backend error reads from its stable `code` (`error.<code>` in
 * `ar/errors.js`); the server's own message is English, and is the fallback.
 * @param {unknown} error @returns {string}
 */
export function errorMessage(error) {
	if (error instanceof NetworkError) {
		return t('Could not reach the server. Check your connection and try again.');
	}
	if (error instanceof ApiError && i18n.locale === 'ar') {
		const translated = AR[`error.${error.code}`];
		if (typeof translated === 'string') return translated;
	}
	if (error instanceof Error && error.message) return error.message;
	return t('Something went wrong.');
}

/**
 * The request field an `ApiError` blamed, if any — for inline form errors
 * like `ValidationDomainError`'s `field` (core/exceptions.py).
 * @param {unknown} error @returns {string|null}
 */
export function errorField(error) {
	return error instanceof ApiError ? error.field : null;
}

/** `"field: message"` when the server named a field, else just the message. @param {unknown} error */
export function formatApiError(error) {
	const field = errorField(error);
	const message = errorMessage(error);
	return field ? `${field}: ${message}` : message;
}
