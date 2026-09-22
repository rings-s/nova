/**
 * Reading and writing a map position as text, for the field an owner can type
 * or paste into (Google Maps and OpenStreetMap both copy `24.7136, 46.6753`).
 * Pure, so it needs no browser and no Leaflet.
 */

/** One decimal number: `24.7`, `-46`, `.5`, `+3.`. Not `1e2`, `0x10`, `NaN`. */
const NUMBER = /^[+-]?(\d+\.?\d*|\.\d+)$/;

const SHAPE = 'Enter latitude and longitude, like 24.7136, 46.6753.';

/**
 * @typedef {{ status: 'empty' }
 *   | { status: 'ok', latitude: number, longitude: number }
 *   | { status: 'invalid', message: string }} ParsedCoordinates
 */

/**
 * Empty is a valid answer: it means "no pin". Anything else has to be exactly
 * two numbers, in range, or the field says why not. The same limits the API
 * enforces (`validate_coordinates` in the catalog module), so an owner learns
 * about a bad position while typing and not from a failed save.
 * @param {string} text
 * @returns {ParsedCoordinates}
 */
export function parseCoordinates(text) {
	const trimmed = text.trim();
	if (!trimmed) return { status: 'empty' };

	const parts = trimmed.split(/[\s,;]+/).filter(Boolean);
	if (parts.length !== 2 || !parts.every((part) => NUMBER.test(part))) {
		return { status: 'invalid', message: SHAPE };
	}
	const [latitude, longitude] = parts.map(Number);
	if (latitude < -90 || latitude > 90) {
		return { status: 'invalid', message: 'Latitude must be between -90 and 90.' };
	}
	if (longitude < -180 || longitude > 180) {
		return { status: 'invalid', message: 'Longitude must be between -180 and 180.' };
	}
	return { status: 'ok', latitude, longitude };
}

/**
 * Six decimals, about ten centimetres: far finer than a shop front needs, and
 * still a short string to read back.
 * @param {number} latitude
 * @param {number} longitude
 */
export function formatCoordinates(latitude, longitude) {
	return `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`;
}

/**
 * A pin dropped by clicking or dragging, rounded to what `formatCoordinates`
 * shows, so the field and the saved value never disagree in the last digit.
 * @param {number} value
 */
export function roundCoordinate(value) {
	return Math.round(value * 1e6) / 1e6;
}
