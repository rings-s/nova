/**
 * discovery — nova_backend/app/modules/discovery/router.py
 *
 * The public marketplace surface. Every route here is unauthenticated and
 * cross-tenant by design (ADR-0010) — a customer browsing has not chosen a
 * salon yet, so there is no tenant to scope to.
 */
import { http } from './client.js';

/**
 * @typedef {Object} ListingCard
 * @property {string} business_id
 * @property {string} tenant_id
 * @property {string} slug
 * @property {string} name_en
 * @property {string} name_ar
 * @property {string|null} description_en
 * @property {string|null} description_ar
 * @property {string|null} logo_asset_id
 * @property {string|null} cover_asset_id
 * @property {string} location_id
 * @property {string} location_name_en
 * @property {string} location_name_ar
 * @property {string|null} city
 * @property {number|null} latitude
 * @property {number|null} longitude
 * @property {string} timezone
 * @property {string|null} starting_price
 * @property {string|null} currency
 * @property {number|null} distance_km
 * @property {number} rating_count Verified ratings received.
 * @property {number|null} rating_average Plain average, 1–5; null when unrated.
 */

/**
 * A branch as a GeoJSON Point Feature (RFC 7946), the shape `L.geoJSON` reads.
 * @typedef {Object} ListingFeature
 * @property {'Feature'} type
 * @property {string} id The branch (location) id.
 * @property {{ type: 'Point', coordinates: [number, number] }} geometry
 *   `[longitude, latitude]` — GeoJSON's order, the reverse of `ListingCard`'s.
 * @property {ListingCard} properties The same public projection a search hit carries.
 */

/**
 * @typedef {Object} ListingFeatureCollection
 * @property {'FeatureCollection'} type
 * @property {ListingFeature[]} features
 * @property {boolean} truncated More branches matched than the response's
 *   `limit` allowed, so the map shows some of them, not all.
 */

/**
 * @typedef {Object} StorefrontLocation
 * @property {string} id
 * @property {string} name_en
 * @property {string} name_ar
 * @property {string|null} city
 * @property {string} phone
 * @property {string} timezone
 * @property {number|null} latitude
 * @property {number|null} longitude
 */

/**
 * @typedef {Object} StorefrontService
 * @property {string} id
 * @property {string} location_id
 * @property {string} name_en
 * @property {string} name_ar
 * @property {string|null} description_en
 * @property {string|null} description_ar
 * @property {string|null} category
 * @property {number} duration_minutes
 * @property {string} price
 * @property {string} currency
 */

/**
 * @typedef {Object} StorefrontProvider
 * @property {string} id
 * @property {string} location_id
 * @property {string} name_en
 * @property {string} name_ar
 * @property {string|null} title_en
 * @property {string|null} title_ar
 * @property {string|null} image_asset_id
 */

/**
 * @typedef {Object} Storefront
 * @property {string} business_id
 * @property {string} tenant_id Needed to book: every booking route is tenant-scoped.
 * @property {string} slug
 * @property {string} name_en
 * @property {string} name_ar
 * @property {string|null} description_en
 * @property {string|null} description_ar
 * @property {string|null} logo_asset_id
 * @property {string|null} cover_asset_id
 * @property {number} rating_count
 * @property {number|null} rating_average
 * @property {StorefrontLocation[]} locations
 * @property {StorefrontService[]} services
 * @property {StorefrontProvider[]} providers
 */

/**
 * @typedef {Object} PublicSlot
 * @property {string} slot_id Signed — hand it straight to `createBooking`.
 * @property {string} provider_id
 * @property {string} provider_name_en
 * @property {string} provider_name_ar
 * @property {string} location_id
 * @property {string} service_id
 * @property {string} starts_at
 * @property {string} ends_at
 */

/**
 * @typedef {Object} PublicAvailability
 * @property {string} business_id
 * @property {string} tenant_id
 * @property {string} service_id
 * @property {string} location_id
 * @property {number} duration_minutes
 * @property {string} price
 * @property {string} currency
 * @property {PublicSlot[]} slots
 */

/**
 * @typedef {Object} Referral
 * @property {string} referral_token Present the token on `createBooking` to
 *   attribute it as `marketplace`. Returned exactly once.
 * @property {string} business_id
 * @property {string} tenant_id
 * @property {string} expires_at
 */

/**
 * Finds bookable branches. The marketplace's front door.
 *
 * `bbox` keeps only branches inside a map viewport, `west,south,east,north`;
 * `toBBox` in `$lib/map/bbox.js` produces it from a Leaflet map.
 *
 * `sort`: `default` is nearest-first when `latitude`/`longitude` are given and
 * by name otherwise; `distance` needs coordinates; `rating` ranks best-rated
 * first by a confidence-weighted score, so one 5-star visit does not outrank
 * hundreds averaging 4.8. Coordinates also limit results to `radiusKm`
 * (default 25).
 * @param {{ q?: string|null, city?: string|null, category?: string|null, latitude?: number|null,
 *   longitude?: number|null, radiusKm?: number|null, bbox?: string|null,
 *   sort?: 'default'|'distance'|'rating', limit?: number, offset?: number }} [params]
 * @returns {Promise<{ items: ListingCard[] }>}
 */
export function searchBusinesses({
	q = null,
	city = null,
	category = null,
	latitude = null,
	longitude = null,
	radiusKm = null,
	bbox = null,
	sort = 'default',
	limit = 20,
	offset = 0
} = {}) {
	return http.get('/discovery/businesses', {
		query: {
			q,
			city,
			category,
			latitude,
			longitude,
			radius_km: radiusKm,
			bbox,
			sort,
			limit,
			offset
		}
	});
}

/**
 * The same search as `searchBusinesses`, as GeoJSON for a Leaflet map: only
 * branches with coordinates, not paged. When `truncated` is true the cap cut
 * some off and the customer should be asked to zoom in.
 * @param {{ q?: string|null, city?: string|null, category?: string|null, bbox?: string|null,
 *   limit?: number }} [params]
 * @returns {Promise<ListingFeatureCollection>}
 */
export function mapBusinesses({ q = null, city = null, category = null, bbox = null, limit } = {}) {
	return http.get('/discovery/map', { query: { q, city, category, bbox, limit } });
}

/** @param {string} slug @returns {Promise<Storefront>} */
export function getStorefront(slug) {
	return http.get(`/discovery/businesses/${slug}`);
}

/**
 * Free slots for one service, across every qualified provider.
 * @param {string} slug @param {string} serviceId
 * @param {{ dateFrom: string, dateTo: string }} params
 * @returns {Promise<PublicAvailability>}
 */
export function getPublicAvailability(slug, serviceId, { dateFrom, dateTo }) {
	return http.get(`/discovery/businesses/${slug}/services/${serviceId}/availability`, {
		query: { date_from: dateFrom, date_to: dateTo }
	});
}

/**
 * Records that NOVA sent this customer to this storefront. Call when a
 * customer opens a listing; keep the token for the eventual `createBooking`.
 * @param {string} slug @returns {Promise<Referral>}
 */
export function recordReferral(slug) {
	return http.post(`/discovery/businesses/${slug}/referrals`);
}
