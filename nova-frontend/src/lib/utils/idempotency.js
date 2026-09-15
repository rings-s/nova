/**
 * `Idempotency-Key` values for retryable POSTs (nova_backend/app/core/idempotency.py).
 * Generate one when a create action *starts* (button press, form mount) and
 * reuse the same value across retries of that one logical attempt — a fresh
 * key on every retry defeats the point.
 */
export function newIdempotencyKey() {
	if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
		return crypto.randomUUID();
	}
	// Fallback for a runtime without `crypto.randomUUID` (very old browsers).
	return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
