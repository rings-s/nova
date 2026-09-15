/**
 * Session state: tokens, and the principal decoded from them for UI purposes
 * (see `$lib/utils/jwt.js` — never treat that decode as verification).
 *
 * A Svelte 5 "universal reactive module": top-level `$state`/`$derived` in a
 * `.svelte.js` file is a singleton store importable from anywhere, no context
 * or provider needed. This is the one place that calls `configureAuth`, so
 * `$lib/api/client.js` can retry a 401 with a refreshed token without ever
 * importing this file back (that would be circular).
 */
import { browser } from '$app/environment';
import { configureAuth } from '../api/client.js';
import * as authApi from '../api/auth.js';
import { decodeJwtPayload } from '../utils/jwt.js';

const STORAGE_KEY = 'nova.auth.v1';

function loadPersisted() {
	if (!browser) return null;
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		return raw ? JSON.parse(raw) : null;
	} catch {
		return null;
	}
}

function persist(value) {
	if (!browser) return;
	try {
		if (value) localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
		else localStorage.removeItem(STORAGE_KEY);
	} catch {
		// Storage unavailable (private mode, quota). The session still works
		// in-memory for the rest of this tab's lifetime.
	}
}

const persisted = loadPersisted();

let accessToken = $state(persisted?.accessToken ?? null);
let refreshToken = $state(persisted?.refreshToken ?? null);
/** @type {'anonymous'|'authenticating'|'authenticated'} */
let status = $state(persisted?.accessToken ? 'authenticated' : 'anonymous');

let principal = $derived(accessToken ? decodeJwtPayload(accessToken) : null);

function save() {
	persist(accessToken ? { accessToken, refreshToken } : null);
}

function clear() {
	accessToken = null;
	refreshToken = null;
	status = 'anonymous';
	save();
}

function applyTokens(tokens) {
	accessToken = tokens.access_token;
	refreshToken = tokens.refresh_token;
	status = 'authenticated';
	save();
}

/** @type {Promise<string>|null} */
let refreshPromise = null;

async function refresh() {
	if (!refreshToken) throw new Error('No refresh token to use.');
	if (!refreshPromise) {
		refreshPromise = authApi
			.refresh(refreshToken)
			.then((tokens) => {
				applyTokens(tokens);
				return accessToken;
			})
			.finally(() => {
				refreshPromise = null;
			});
	}
	return refreshPromise;
}

configureAuth({
	getAccessToken: () => accessToken,
	refresh,
	onUnauthorized: clear
});

export const authStore = {
	get accessToken() {
		return accessToken;
	},
	get status() {
		return status;
	},
	get isAuthenticated() {
		return status === 'authenticated';
	},
	/** Decoded token claims: `{ sub, kind, tenants, roles, exp, iat }`. Display only. */
	get principal() {
		return principal;
	},
	get isStaff() {
		return principal?.kind === 'staff' || principal?.kind === 'service';
	},
	/** Tenant ids baked into the current access token at login. */
	get tenantIds() {
		return /** @type {string[]} */ (principal?.tenants ?? []);
	},
	/** Roles flattened across every tenant the user belongs to — never use this
	 *  for a per-tenant permission check; the server settles those from the
	 *  tenant's own membership row regardless of what this claims. */
	get roles() {
		return /** @type {string[]} */ (principal?.roles ?? []);
	},

	/** @param {{ email: string, password: string }} credentials */
	async login(credentials) {
		status = 'authenticating';
		try {
			const tokens = await authApi.login(credentials);
			applyTokens(tokens);
			return tokens;
		} catch (err) {
			status = 'anonymous';
			throw err;
		}
	},

	/** @param {{ email: string, password: string, fullName: string, phone?: string|null }} params */
	register(params) {
		return authApi.register(params);
	},

	/** Ends every outstanding token for this account, everywhere, then clears locally. */
	async logoutEverywhere() {
		if (accessToken) {
			await authApi.logoutEverywhere().catch(() => {});
		}
		clear();
	},

	/** Clears this tab's session only, without revoking the refresh token elsewhere. */
	logout() {
		clear();
	},

	requestPhoneVerification() {
		return authApi.requestPhoneVerification();
	},

	/** @param {string} token */
	confirmPhoneVerification(token) {
		return authApi.confirmPhoneVerification(token);
	}
};
