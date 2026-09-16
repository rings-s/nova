/**
 * catalog — nova_backend/app/modules/catalog/router.py
 *
 * Where a business operates (locations) and what it sells (services), and who
 * performs them (providers). Reads are open to any caller with tenant access;
 * every write is staff-only, enforced server-side.
 */
import { http, tenantPath } from './client.js';

/**
 * @typedef {Object} Business
 * @property {string} id
 * @property {string} tenant_id
 * @property {string} name_en
 * @property {string} name_ar
 * @property {string} slug
 * @property {string|null} description_en
 * @property {string|null} description_ar
 * @property {string|null} logo_asset_id
 * @property {string|null} cover_asset_id
 * @property {boolean} is_active
 * @property {boolean} is_listed Advertised on the public marketplace.
 * @property {string} created_at
 * @property {string} updated_at
 */

/**
 * @typedef {Object} Location
 * @property {string} id
 * @property {string} tenant_id
 * @property {string} business_id
 * @property {string} name_en
 * @property {string} name_ar
 * @property {string} slug
 * @property {string} phone
 * @property {string} timezone
 * @property {string|null} city
 * @property {number|null} latitude
 * @property {number|null} longitude
 * @property {boolean} is_active
 * @property {string} created_at
 * @property {string} updated_at
 */

/**
 * @typedef {Object} Service
 * @property {string} id
 * @property {string} tenant_id
 * @property {string} location_id
 * @property {string} name_en
 * @property {string} name_ar
 * @property {string|null} description_en
 * @property {string|null} description_ar
 * @property {string|null} category
 * @property {number} duration_minutes
 * @property {string} price Decimal, serialised as a string or number.
 * @property {string} currency
 * @property {boolean} is_active
 * @property {string} created_at
 * @property {string} updated_at
 */

/**
 * @typedef {Object} Provider
 * @property {string} id
 * @property {string} tenant_id
 * @property {string} location_id
 * @property {string} name_en
 * @property {string} name_ar
 * @property {string|null} title_en
 * @property {string|null} title_ar
 * @property {string|null} image_asset_id
 * @property {boolean} is_active
 * @property {string} created_at
 * @property {string} updated_at
 */

// --- Businesses --------------------------------------------------------------

/**
 * @param {string} tenantId
 * @param {{ nameEn: string, nameAr: string, descriptionEn?: string|null, descriptionAr?: string|null }} params
 * @returns {Promise<Business>}
 */
export function createBusiness(
	tenantId,
	{ nameEn, nameAr, descriptionEn = null, descriptionAr = null }
) {
	return http.post(tenantPath(tenantId, '/catalog/businesses'), {
		name_en: nameEn,
		name_ar: nameAr,
		description_en: descriptionEn,
		description_ar: descriptionAr
	});
}

/** @param {string} tenantId @param {string} businessId @returns {Promise<Business>} */
export function getBusiness(tenantId, businessId) {
	return http.get(tenantPath(tenantId, `/catalog/businesses/${businessId}`));
}

/**
 * Shows or hides this business on the public marketplace.
 * @param {string} tenantId @param {string} businessId @param {boolean} isListed
 * @returns {Promise<Business>}
 */
export function setListingVisibility(tenantId, businessId, isListed) {
	return http.patch(tenantPath(tenantId, `/catalog/businesses/${businessId}/listing`), {
		is_listed: isListed
	});
}

// --- Locations -----------------------------------------------------------

/**
 * @param {string} tenantId
 * @param {{ businessId: string, nameEn: string, nameAr: string, phone: string, timezone?: string,
 *   city?: string|null, latitude?: number|null, longitude?: number|null }} params
 * @returns {Promise<Location>}
 */
export function createLocation(
	tenantId,
	{
		businessId,
		nameEn,
		nameAr,
		phone,
		timezone = 'Asia/Riyadh',
		city = null,
		latitude = null,
		longitude = null
	}
) {
	return http.post(tenantPath(tenantId, '/catalog/locations'), {
		business_id: businessId,
		name_en: nameEn,
		name_ar: nameAr,
		phone,
		timezone,
		city,
		latitude,
		longitude
	});
}

/** @param {string} tenantId @param {string} businessId @returns {Promise<{ items: Location[], total: number|null }>} */
export function listLocations(tenantId, businessId) {
	return http.get(tenantPath(tenantId, `/catalog/businesses/${businessId}/locations`));
}

// --- Services --------------------------------------------------------------

/**
 * @param {string} tenantId
 * @param {{ locationId: string, nameEn: string, nameAr: string, descriptionEn?: string|null,
 *   descriptionAr?: string|null, category?: string|null, durationMinutes: number,
 *   price: string|number, currency?: string }} params
 * @returns {Promise<Service>}
 */
export function createService(
	tenantId,
	{
		locationId,
		nameEn,
		nameAr,
		descriptionEn = null,
		descriptionAr = null,
		category = null,
		durationMinutes,
		price,
		currency = 'SAR'
	}
) {
	return http.post(tenantPath(tenantId, '/catalog/services'), {
		location_id: locationId,
		name_en: nameEn,
		name_ar: nameAr,
		description_en: descriptionEn,
		description_ar: descriptionAr,
		category,
		duration_minutes: durationMinutes,
		price,
		currency
	});
}

/** @param {string} tenantId @param {string} locationId @returns {Promise<{ items: Service[], total: number|null }>} */
export function listServices(tenantId, locationId) {
	return http.get(tenantPath(tenantId, `/catalog/locations/${locationId}/services`));
}

// --- Providers ---------------------------------------------------------------

/**
 * @param {string} tenantId
 * @param {{ locationId: string, nameEn: string, nameAr: string, titleEn?: string|null, titleAr?: string|null }} params
 * @returns {Promise<Provider>}
 */
export function createProvider(
	tenantId,
	{ locationId, nameEn, nameAr, titleEn = null, titleAr = null }
) {
	return http.post(tenantPath(tenantId, '/catalog/providers'), {
		location_id: locationId,
		name_en: nameEn,
		name_ar: nameAr,
		title_en: titleEn,
		title_ar: titleAr
	});
}

/** @param {string} tenantId @param {string} locationId @returns {Promise<{ items: Provider[], total: number|null }>} */
export function listProviders(tenantId, locationId) {
	return http.get(tenantPath(tenantId, `/catalog/locations/${locationId}/providers`));
}

/**
 * Qualifies a provider to perform a service.
 * @param {string} tenantId @param {string} providerId @param {string} serviceId
 */
export function assignServiceToProvider(tenantId, providerId, serviceId) {
	return http.post(tenantPath(tenantId, `/catalog/providers/${providerId}/services`), {
		service_id: serviceId
	});
}
