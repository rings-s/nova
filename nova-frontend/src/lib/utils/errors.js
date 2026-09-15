/**
 * Turns a thrown value — an `ApiError`, a `NetworkError`, or anything else —
 * into text a form or toast can show. Centralised so every `catch` block
 * reads the same way instead of reaching into `err.message` under `unknown`.
 */
import { ApiError } from '../api/client.js';

/** @param {unknown} error @returns {string} */
export function errorMessage(error) {
	if (error instanceof Error) return error.message;
	return 'Something went wrong.';
}

/**
 * The request field an `ApiError` blamed, if any — for inline form errors
 * like `ValidationDomainError`'s `field` (core/exceptions.py).
 * @param {unknown} error @returns {string|null}
 */
export function errorField(error) {
	return error instanceof ApiError ? error.field : null;
}

/** `"field: message"` when the server named a field, else just the message. */
export function formatApiError(error) {
	const field = errorField(error);
	const message = errorMessage(error);
	return field ? `${field}: ${message}` : message;
}
