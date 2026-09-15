/**
 * identity — nova_backend/app/modules/identity/router.py
 *
 * Tenants (businesses on the platform), their customers, and staff memberships.
 */
import { http, tenantPath } from './client.js';

/**
 * @typedef {Object} Tenant
 * @property {string} id
 * @property {string} name_en
 * @property {string} name_ar
 * @property {string} slug
 * @property {string} phone
 * @property {string} default_currency
 * @property {string} created_at
 * @property {string} updated_at
 */

/**
 * @typedef {Object} Customer
 * @property {string} id
 * @property {string} tenant_id
 * @property {string} full_name
 * @property {string} phone
 * @property {string|null} email
 * @property {string} preferred_language
 * @property {boolean} marketing_consent
 * @property {boolean} whatsapp_consent
 * @property {string|null} notes
 * @property {string} created_at
 * @property {string} updated_at
 */

/**
 * @typedef {'owner'|'manager'|'receptionist'|'provider'} MembershipRole
 */

/**
 * @typedef {Object} Membership
 * @property {string} id
 * @property {string} tenant_id
 * @property {string} user_id
 * @property {string} email
 * @property {string} full_name
 * @property {MembershipRole} role
 * @property {boolean} is_active
 * @property {string} created_at
 * @property {string} updated_at
 */

/**
 * @typedef {Object} MembershipInvite
 * @property {string} id
 * @property {string} tenant_id
 * @property {string} email
 * @property {MembershipRole} role
 * @property {string} token Shown once, at creation — relay it out of band.
 * @property {string} expires_at
 * @property {string} created_at
 */

/**
 * @typedef {Object} MembershipInviteSummary
 * @property {string} id
 * @property {string} tenant_id
 * @property {string} email
 * @property {MembershipRole} role
 * @property {string} expires_at
 * @property {string} created_at
 */

// --- Tenants ---------------------------------------------------------------

/**
 * Registers a business. The caller becomes its owner — refresh the access
 * token afterwards so it carries the new membership.
 * @param {{ nameEn: string, nameAr: string, phone: string, defaultCurrency?: string }} params
 * @returns {Promise<Tenant>}
 */
export function createTenant({ nameEn, nameAr, phone, defaultCurrency = 'SAR' }) {
	return http.post('/tenants', {
		name_en: nameEn,
		name_ar: nameAr,
		phone,
		default_currency: defaultCurrency
	});
}

/** The caller's own businesses. @returns {Promise<{ items: Tenant[], total: number|null }>} */
export function listMyTenants({ limit = 20, offset = 0 } = {}) {
	return http.get('/tenants', { query: { limit, offset } });
}

/** @returns {Promise<Tenant>} */
export function getTenant(tenantId) {
	return http.get(tenantPath(tenantId));
}

// --- Customers (staff only) -------------------------------------------------

/**
 * @param {string} tenantId
 * @param {{ fullName: string, phone: string, email?: string|null, preferredLanguage?: string|null,
 *   marketingConsent?: boolean, whatsappConsent?: boolean, notes?: string|null }} params
 * @returns {Promise<Customer>}
 */
export function createCustomer(
	tenantId,
	{
		fullName,
		phone,
		email = null,
		preferredLanguage = null,
		marketingConsent = false,
		whatsappConsent = false,
		notes = null
	}
) {
	return http.post(tenantPath(tenantId, '/customers'), {
		full_name: fullName,
		phone,
		email,
		preferred_language: preferredLanguage,
		marketing_consent: marketingConsent,
		whatsapp_consent: whatsappConsent,
		notes
	});
}

/** @returns {Promise<{ items: Customer[], total: number|null }>} */
export function listCustomers(tenantId, { q = null, limit = 20, offset = 0 } = {}) {
	return http.get(tenantPath(tenantId, '/customers'), { query: { q, limit, offset } });
}

/** @returns {Promise<Customer>} */
export function getCustomer(tenantId, customerId) {
	return http.get(tenantPath(tenantId, `/customers/${customerId}`));
}

/**
 * PDPL: withdrawing consent must be as easy as giving it.
 * @returns {Promise<Customer>}
 */
export function updateCustomerConsent(
	tenantId,
	customerId,
	{ marketingConsent = null, whatsappConsent = null }
) {
	return http.patch(tenantPath(tenantId, `/customers/${customerId}/consent`), {
		marketing_consent: marketingConsent,
		whatsapp_consent: whatsappConsent
	});
}

// --- Memberships (staff only) ------------------------------------------------

/** @returns {Promise<{ items: Membership[], total: number|null }>} */
export function listMemberships(tenantId, { limit = 20, offset = 0 } = {}) {
	return http.get(tenantPath(tenantId, '/memberships'), { query: { limit, offset } });
}

/**
 * Starts staff access for `email`. The returned token is the entire
 * credential — relay it to the person out of band; NOVA never delivers it.
 * @returns {Promise<MembershipInvite>}
 */
export function inviteMembership(tenantId, { email, role }) {
	return http.post(tenantPath(tenantId, '/memberships'), { email, role });
}

/** @returns {Promise<{ items: MembershipInviteSummary[], total: number|null }>} */
export function listPendingInvites(tenantId, { limit = 20, offset = 0 } = {}) {
	return http.get(tenantPath(tenantId, '/memberships/invites'), { query: { limit, offset } });
}

/** @returns {Promise<Membership>} */
export function acceptMembershipInvite(tenantId, inviteId, token) {
	return http.post(tenantPath(tenantId, `/memberships/invites/${inviteId}/accept`), { token });
}

/** @returns {Promise<Membership>} */
export function changeMembershipRole(tenantId, membershipId, role) {
	return http.patch(tenantPath(tenantId, `/memberships/${membershipId}`), { role });
}

/** 409 when it would leave the business with no owner. @returns {Promise<Membership>} */
export function revokeMembership(tenantId, membershipId) {
	return http.delete(tenantPath(tenantId, `/memberships/${membershipId}`));
}
