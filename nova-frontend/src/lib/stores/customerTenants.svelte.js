/**
 * Which tenants the signed-in customer has booked with — the backend has no
 * "list my bookings across every tenant" endpoint (`GET .../bookings` is
 * tenant-scoped: nova_backend/app/modules/booking/router.py), and a customer
 * is free to book with any salon on the marketplace, so there is no single id
 * to key that read on. The frontend remembers the tenants a booking actually
 * succeeded against, the moment it happens (`discover/[slug]`'s booking
 * flow), and `/bookings` loops over this list — same shape of workaround, and
 * same limitation, as `businessStore`. A customer's history on a browser that
 * never made those bookings is invisible until the backend adds a real
 * cross-tenant read.
 */
import { browser } from '$app/environment';

const STORAGE_KEY = 'nova.customerTenants';

/** @typedef {{ tenantId: string, businessName: string }} KnownTenant */

function load() {
	if (!browser) return /** @type {KnownTenant[]} */ ([]);
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		return raw ? JSON.parse(raw) : [];
	} catch {
		return [];
	}
}

let known = $state(/** @type {KnownTenant[]} */ (load()));

function persist() {
	if (!browser) return;
	try {
		localStorage.setItem(STORAGE_KEY, JSON.stringify(known));
	} catch {
		// Storage unavailable — the list still holds for this tab.
	}
}

export const customerTenantsStore = {
	get all() {
		return known;
	},
	/** @param {string} tenantId @param {string} businessName */
	add(tenantId, businessName) {
		if (known.some((entry) => entry.tenantId === tenantId)) return;
		known = [...known, { tenantId, businessName }];
		persist();
	}
};
