/**
 * Reads the claims out of a JWT the backend already issued and this client
 * already holds — for UI purposes only (which tenants, which role, when it
 * expires). This is NOT verification: the signature is never checked here,
 * because the browser has no way to and must not be trusted to. The server
 * (`app/core/security.py`) is the only party that verifies a token; treat
 * anything read here as a display hint, never as an authorization decision.
 */

/** @param {string|null|undefined} token @returns {Record<string, unknown>|null} */
export function decodeJwtPayload(token) {
	if (!token) return null;
	try {
		const [, payload] = token.split('.');
		if (!payload) return null;
		const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
		const padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4);
		const binary = atob(padded);
		const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
		const json = new TextDecoder().decode(bytes);
		return JSON.parse(json);
	} catch {
		return null;
	}
}

/** @param {Record<string, unknown>|null} claims */
export function isExpired(claims, { leewaySeconds = 0 } = {}) {
	if (!claims || typeof claims.exp !== 'number') return true;
	return Date.now() / 1000 > claims.exp + leewaySeconds;
}
