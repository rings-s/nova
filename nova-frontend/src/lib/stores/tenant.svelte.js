/**
 * Which tenant the UI is currently acting on. `tenant_id` in the API always
 * comes from the URL path (see CLAUDE.md, "Authorization") — this store is
 * only where the client remembers the last choice between visits; every
 * request still gets its tenant id from the page's own route params.
 */
import { browser } from '$app/environment';

const STORAGE_KEY = 'nova.activeTenantId';

function loadPersisted() {
	if (!browser) return null;
	try {
		return localStorage.getItem(STORAGE_KEY);
	} catch {
		return null;
	}
}

let activeTenantId = $state(loadPersisted());

export const tenantStore = {
	get activeTenantId() {
		return activeTenantId;
	},
	/** @param {string|null} tenantId */
	set(tenantId) {
		activeTenantId = tenantId;
		if (!browser) return;
		try {
			if (tenantId) localStorage.setItem(STORAGE_KEY, tenantId);
			else localStorage.removeItem(STORAGE_KEY);
		} catch {
			// Storage unavailable — the choice still holds for this tab.
		}
	},
	clear() {
		this.set(null);
	}
};
