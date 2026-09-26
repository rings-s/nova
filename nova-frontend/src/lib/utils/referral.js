/**
 * Carries a storefront's referral token (`recordReferral`, discovery.js) from
 * the storefront to its booking page, so the booking is still attributed
 * `marketplace` (ADR-0008) without recording a second click. Kept in
 * sessionStorage, per slug, until it expires; storage that is blocked or
 * empty just means no token, never an error.
 */

/** @param {string} slug */
const storageKey = (slug) => `nova_referral:${slug}`;

/** @param {string} slug @param {import('../api/discovery.js').Referral} referral */
export function rememberReferral(slug, referral) {
	try {
		sessionStorage.setItem(
			storageKey(slug),
			JSON.stringify({ token: referral.referral_token, expiresAt: referral.expires_at })
		);
	} catch {
		// Storage blocked: the booking just goes unattributed.
	}
}

/** @param {string} slug @returns {string|null} */
export function recallReferral(slug) {
	try {
		const raw = sessionStorage.getItem(storageKey(slug));
		if (!raw) return null;
		const { token, expiresAt } = JSON.parse(raw);
		if (typeof token !== 'string' || new Date(expiresAt).getTime() <= Date.now()) return null;
		return token;
	} catch {
		return null;
	}
}
