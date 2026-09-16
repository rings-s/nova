/**
 * Which `catalog.Business` the dashboard is managing for the active tenant.
 *
 * A real gap in the backend's catalog module: there is no `GET` that lists
 * the businesses under a tenant (`catalog/router.py` only has create-by-POST
 * and get-by-id) — see nova_backend/app/modules/catalog/router.py. The
 * business id is only ever handed to a client once, in the create response,
 * so this is the one place the frontend remembers it. `createBusiness`
 * (identity/register flow) and the catalog "set up your storefront" fallback
 * both call `set()` the moment they get an id back.
 *
 * Keyed by tenant, since a browser can hold sessions for staff at more than
 * one business. This has no recovery path for staff who were invited to an
 * existing tenant on a browser that never cached its business id — the
 * proper fix is a `GET /tenants/{id}/catalog/businesses` endpoint; until
 * then the catalog page's empty state can only offer to create a new one,
 * which is wrong for that case. Flagged rather than silently worked around.
 */
import { browser } from '$app/environment';
import { tenantStore } from './tenant.svelte.js';

const STORAGE_KEY = 'nova.businessByTenant';

function loadMap() {
	if (!browser) return {};
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		return raw ? JSON.parse(raw) : {};
	} catch {
		return {};
	}
}

/** @type {Record<string, string>} */
let businessByTenant = $state(loadMap());

function persist() {
	if (!browser) return;
	try {
		localStorage.setItem(STORAGE_KEY, JSON.stringify(businessByTenant));
	} catch {
		// Storage unavailable — the choice still holds for this tab.
	}
}

export const businessStore = {
	get activeBusinessId() {
		const tenantId = tenantStore.activeTenantId;
		return tenantId ? (businessByTenant[tenantId] ?? null) : null;
	},
	/** @param {string} tenantId @param {string} businessId */
	set(tenantId, businessId) {
		businessByTenant = { ...businessByTenant, [tenantId]: businessId };
		persist();
	},
	/** @param {string} tenantId */
	clear(tenantId) {
		if (!(tenantId in businessByTenant)) return;
		const next = { ...businessByTenant };
		delete next[tenantId];
		businessByTenant = next;
		persist();
	}
};
