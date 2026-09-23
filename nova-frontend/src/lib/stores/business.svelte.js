/**
 * Which `catalog.Business` the dashboard is managing for the active tenant.
 *
 * A cache, not the source of truth: `routes/app/+layout.svelte` fills it from
 * `GET /tenants/{id}/catalog/businesses` whenever this browser doesn't know
 * the tenant's business yet — a new device, a cleared browser, or staff
 * invited to an existing salon. Registration and the catalog's "create your
 * storefront" form also `set()` it the moment they get an id back.
 *
 * Keyed by tenant, since a browser can hold sessions for staff at more than
 * one business.
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
