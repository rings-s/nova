/**
 * A map viewport as the `bbox` query parameter the discovery API takes:
 * `west,south,east,north` in degrees, which is the order Leaflet's own
 * `toBBoxString()` uses (see `parse_bbox` in
 * nova_backend/app/modules/discovery/domain.py).
 *
 * Clamped first, because a map zoomed out far enough shows the world more than
 * once and Leaflet then reports a west of -300 or an east of 400, which the API
 * refuses. Rounded to five decimals, about a metre, to keep the URL short.
 *
 * Takes anything with the four getters, so it needs no Leaflet import and
 * stays usable on the server.
 * @param {{ getWest(): number, getSouth(): number, getEast(): number, getNorth(): number }} bounds
 * @returns {string}
 */
export function toBBox(bounds) {
	/** @param {number} value @param {number} limit */
	const clamp = (value, limit) => Math.min(limit, Math.max(-limit, value));
	/** @param {number} value */
	const round = (value) => Math.round(value * 1e5) / 1e5;

	return [
		clamp(bounds.getWest(), 180),
		clamp(bounds.getSouth(), 90),
		clamp(bounds.getEast(), 180),
		clamp(bounds.getNorth(), 90)
	]
		.map(round)
		.join(',');
}
