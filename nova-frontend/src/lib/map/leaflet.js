/**
 * The Leaflet set-up every NOVA map repeats: loading the library, drawing the
 * OpenStreetMap layer, and drawing a pin. The maps themselves
 * (`ListingsMap`, `LocationPicker`) own everything that differs.
 */
import { MAX_ZOOM, TILE_ATTRIBUTION, TILE_URL } from './config.js';

/**
 * Leaflet reads `window` when it is imported, so it can only be loaded in the
 * browser: call this from `onMount`, never from the top of a component that
 * also renders on the server.
 * @returns {Promise<typeof import('leaflet')>}
 */
export async function loadLeaflet() {
	const mod = await import('leaflet');
	return /** @type {typeof import('leaflet')} */ (/** @type {any} */ (mod).default ?? mod);
}

/**
 * The OpenStreetMap layer, with the credit its licence requires.
 * @param {typeof import('leaflet')} L
 * @param {import('leaflet').Map} map
 */
export function addBaseLayer(L, map) {
	return L.tileLayer(TILE_URL, { attribution: TILE_ATTRIBUTION, maxZoom: MAX_ZOOM }).addTo(map);
}

/**
 * One pin, as a DOM node rather than an HTML string: a business names its own
 * listing, and the listings map is public, so nothing a tenant typed is ever
 * parsed as markup. A fresh node per marker, because Leaflet moves the node it
 * is given into the icon rather than copying it.
 * @param {typeof import('leaflet')} L
 */
export function pinIcon(L) {
	const dot = document.createElement('div');
	dot.className =
		'size-7 rounded-full border-[3px] border-white bg-brand-600 shadow-lg ring-1 ring-black/15 transition-transform hover:scale-110';
	return L.divIcon({ html: dot, className: '', iconSize: [28, 28], iconAnchor: [14, 14] });
}
