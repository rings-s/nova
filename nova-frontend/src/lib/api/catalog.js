/**
 * catalog — nova_backend/app/modules/catalog/router.py
 *
 * Where a business operates (locations) and what it sells (services), and who
 * performs them (providers). Reads are open to any caller with tenant access;
 * every write is staff-only, enforced server-side.
 */
import { http, tenantPath } from './client.js';

/**
 * The body of a partial update: `undefined` means "not sent", so the field is
 * left out; `null` is kept, and clears a field that may be empty.
 * @param {Record<string, unknown>} fields
 */
function defined(fields) {
	return Object.fromEntries(Object.entries(fields).filter(([, value]) => value !== undefined));
}

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
 * @property {number} rating_count Verified ratings received.
 * @property {number|null} rating_average Plain average, 1–5; null when unrated.
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
 * @property {string} timezone
 * @property {string|null} city
 * @property {number|null} latitude
 * @property {number|null} longitude
 * @property {boolean} is_active
 * @property {string} created_at
 * @property {string} updated_at
 */

/**
 * A service category from the platform's list, which only a NOVA administrator
 * edits. Salons choose from it (`listCategories` in discovery.js).
 * @typedef {Object} Category
 * @property {string} id
 * @property {string} slug
 * @property {string} name_en
 * @property {string} name_ar
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
 * @property {string|null} category_id
 * @property {Category|null} category
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

/**
 * @typedef {Object} BusinessPhoto
 * @property {string} id
 * @property {string} business_id
 * @property {'cover'|'gallery'} kind
 * @property {number} position
 * @property {number} width
 * @property {number} height
 * @property {string} created_at
 * @property {{ large: string, thumb: string }} urls Short-lived signed links
 *   (paths — pass through `apiAssetUrl`), valid before the business is listed.
 */

/**
 * The cover and gallery, cover first. Staff only.
 * @param {string} tenantId @param {string} businessId @returns {Promise<BusinessPhoto[]>}
 */
export function listBusinessPhotos(tenantId, businessId) {
	return http.get(tenantPath(tenantId, `/catalog/businesses/${businessId}/photos`));
}

/**
 * Makes a photo the cover (the old cover joins the gallery), or sets a gallery
 * photo's place in the order. Owners and managers.
 * @param {string} tenantId @param {string} photoId
 * @param {{ kind?: 'cover'|'gallery', position?: number }} changes
 * @returns {Promise<BusinessPhoto>}
 */
export function updateBusinessPhoto(tenantId, photoId, { kind, position }) {
	return http.patch(
		tenantPath(tenantId, `/catalog/photos/${photoId}`),
		defined({ kind, position })
	);
}

/**
 * Uploads a photo (JPEG, PNG or WebP, the file itself as the body). A new
 * cover replaces the old one. Owners and managers only.
 * @param {string} tenantId @param {string} businessId @param {File|Blob} file
 * @param {'cover'|'gallery'} kind @returns {Promise<BusinessPhoto>}
 */
export function uploadBusinessPhoto(tenantId, businessId, file, kind) {
	return http.post(tenantPath(tenantId, `/catalog/businesses/${businessId}/photos`), file, {
		query: { kind }
	});
}

/** @param {string} tenantId @param {string} photoId @returns {Promise<null>} */
export function deleteBusinessPhoto(tenantId, photoId) {
	return http.delete(tenantPath(tenantId, `/catalog/photos/${photoId}`));
}

/**
 * This salon's storefronts, oldest first. Staff only. How the dashboard finds
 * its business on a device that never saw it being created.
 * @param {string} tenantId @returns {Promise<{ items: Business[] }>}
 */
export function listBusinesses(tenantId) {
	return http.get(tenantPath(tenantId, '/catalog/businesses'));
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
 * @param {{ businessId: string, nameEn: string, nameAr: string, timezone?: string,
 *   city?: string|null, latitude?: number|null, longitude?: number|null }} params
 * @returns {Promise<Location>}
 */
export function createLocation(
	tenantId,
	{
		businessId,
		nameEn,
		nameAr,
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
		timezone,
		city,
		latitude,
		longitude
	});
}

/**
 * Puts a branch on the marketplace map, moves it, or takes it off. Send both
 * numbers, or both as null to remove the pin (the API refuses a half pair).
 * @param {string} tenantId
 * @param {string} locationId
 * @param {{ latitude: number|null, longitude: number|null }} position
 * @returns {Promise<Location>}
 */
export function setLocationPosition(tenantId, locationId, { latitude, longitude }) {
	return http.patch(tenantPath(tenantId, `/catalog/locations/${locationId}/position`), {
		latitude,
		longitude
	});
}

/**
 * Renames a branch, or changes its city, timezone or whether it takes bookings.
 * Only the fields given change; `city: null` clears it. Owners and managers.
 * @param {string} tenantId @param {string} locationId
 * @param {{ nameEn?: string, nameAr?: string, city?: string|null, timezone?: string, isActive?: boolean }} changes
 * @returns {Promise<Location>}
 */
export function updateLocation(tenantId, locationId, { nameEn, nameAr, city, timezone, isActive }) {
	return http.patch(
		tenantPath(tenantId, `/catalog/locations/${locationId}`),
		defined({ name_en: nameEn, name_ar: nameAr, city, timezone, is_active: isActive })
	);
}

/**
 * Deletes a branch with its services and providers. Refused with 409
 * `catalog_item_in_use` while it has an upcoming booking.
 * @param {string} tenantId @param {string} locationId @returns {Promise<null>}
 */
export function deleteLocation(tenantId, locationId) {
	return http.delete(tenantPath(tenantId, `/catalog/locations/${locationId}`));
}

/** @param {string} tenantId @param {string} businessId @returns {Promise<{ items: Location[], total: number|null }>} */
export function listLocations(tenantId, businessId) {
	return http.get(tenantPath(tenantId, `/catalog/businesses/${businessId}/locations`));
}

// --- Services --------------------------------------------------------------

/**
 * @param {string} tenantId
 * @param {{ locationId: string, nameEn: string, nameAr: string, descriptionEn?: string|null,
 *   descriptionAr?: string|null, categoryId?: string|null, durationMinutes: number,
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
		categoryId = null,
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
		category_id: categoryId,
		duration_minutes: durationMinutes,
		price,
		currency
	});
}

/**
 * Only the fields given change; `categoryId: null` clears the category.
 * Bookings already made keep their price and times. Owners and managers.
 * @param {string} tenantId @param {string} serviceId
 * @param {{ nameEn?: string, nameAr?: string, descriptionEn?: string|null, descriptionAr?: string|null,
 *   categoryId?: string|null, durationMinutes?: number, price?: string|number, isActive?: boolean }} changes
 * @returns {Promise<Service>}
 */
export function updateService(
	tenantId,
	serviceId,
	{ nameEn, nameAr, descriptionEn, descriptionAr, categoryId, durationMinutes, price, isActive }
) {
	return http.patch(
		tenantPath(tenantId, `/catalog/services/${serviceId}`),
		defined({
			name_en: nameEn,
			name_ar: nameAr,
			description_en: descriptionEn,
			description_ar: descriptionAr,
			category_id: categoryId,
			duration_minutes: durationMinutes,
			price,
			is_active: isActive
		})
	);
}

/**
 * Refused with 409 `catalog_item_in_use` while it has an upcoming booking.
 * @param {string} tenantId @param {string} serviceId @returns {Promise<null>}
 */
export function deleteService(tenantId, serviceId) {
	return http.delete(tenantPath(tenantId, `/catalog/services/${serviceId}`));
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

/**
 * Renames a provider, changes their title, or takes them off the booking list
 * (`isActive`). Only the fields given change; `null` clears a title.
 * @param {string} tenantId @param {string} providerId
 * @param {{ nameEn?: string, nameAr?: string, titleEn?: string|null, titleAr?: string|null, isActive?: boolean }} changes
 * @returns {Promise<Provider>}
 */
export function updateProvider(
	tenantId,
	providerId,
	{ nameEn, nameAr, titleEn, titleAr, isActive }
) {
	return http.patch(
		tenantPath(tenantId, `/catalog/providers/${providerId}`),
		defined({
			name_en: nameEn,
			name_ar: nameAr,
			title_en: titleEn,
			title_ar: titleAr,
			is_active: isActive
		})
	);
}

/**
 * Refused with 409 `catalog_item_in_use` while they have an upcoming booking.
 * @param {string} tenantId @param {string} providerId @returns {Promise<null>}
 */
export function deleteProvider(tenantId, providerId) {
	return http.delete(tenantPath(tenantId, `/catalog/providers/${providerId}`));
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
