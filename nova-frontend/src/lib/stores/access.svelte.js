/**
 * What the signed-in staff member may do in the business they are managing:
 * their role there, the permissions it carries, and the roles they may manage.
 *
 * Loaded per tenant from `GET /memberships/me` (the tenant's membership row),
 * never from the token's `roles` claim, which merges every business the user
 * works at — an owner of one salon who answers the phone at another would
 * otherwise see owner screens in both. This only decides what to *show*;
 * every request is still authorized by the server.
 */
import { getMyAccess } from '../api/identity.js';

/** @type {import('../api/identity.js').MyAccess|null} */
let access = $state(null);
/** @type {string|null} */
let loadedFor = $state(null);
let loading = $state(false);

export const accessStore = {
	get loaded() {
		return access !== null;
	},
	get loading() {
		return loading;
	},
	get role() {
		return access?.role ?? null;
	},
	/** @param {import('../api/identity.js').StaffPermission} permission */
	can(permission) {
		return access?.permissions.includes(permission) ?? false;
	},
	/** @param {import('../api/identity.js').MembershipRole} role */
	canManage(role) {
		return access?.manageable_roles.includes(role) ?? false;
	},
	get manageableRoles() {
		return access?.manageable_roles ?? [];
	},
	/**
	 * Loads access for `tenantId` unless already loaded for this user there.
	 * Keyed on the user too, so signing in as someone else in the same tab
	 * never shows the previous person's screens.
	 * @param {string} tenantId @param {string} [userId]
	 */
	async load(tenantId, userId = '') {
		const key = `${userId}:${tenantId}`;
		if (loadedFor === key && access) return;
		access = null;
		loading = true;
		loadedFor = key;
		try {
			const result = await getMyAccess(tenantId);
			// A switch to another business may have happened meanwhile.
			// Anything not shaped like an answer counts as no access (fail closed).
			if (loadedFor === key)
				access = {
					role: result?.role ?? null,
					permissions: Array.isArray(result?.permissions) ? result.permissions : [],
					manageable_roles: Array.isArray(result?.manageable_roles) ? result.manageable_roles : []
				};
		} catch {
			// Fail closed: nothing extra is shown, the server decides anyway.
			if (loadedFor === key) access = { role: null, permissions: [], manageable_roles: [] };
		} finally {
			if (loadedFor === key) loading = false;
		}
	},
	clear() {
		access = null;
		loadedFor = null;
	}
};
