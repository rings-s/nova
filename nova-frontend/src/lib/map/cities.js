/**
 * Where a map should open when an owner has typed a city, so placing a pin
 * starts in the right district and not over the whole Gulf.
 *
 * Only a starting view. Nothing here is saved or sent anywhere, and a city the
 * table does not know simply leaves the map where it was: the owner can still
 * pan, type coordinates, or use their location. English and Arabic spellings
 * both work, because the city field is free text.
 *
 * @type {{ names: string[], center: [number, number] }[]}
 */
const CITIES = [
	{ names: ['riyadh', 'الرياض'], center: [24.7136, 46.6753] },
	{ names: ['jeddah', 'jiddah', 'جدة'], center: [21.4858, 39.1925] },
	{ names: ['makkah', 'mecca', 'مكة', 'مكة المكرمة'], center: [21.3891, 39.8579] },
	{ names: ['madinah', 'medina', 'المدينة', 'المدينة المنورة'], center: [24.5247, 39.5692] },
	{ names: ['dammam', 'الدمام'], center: [26.4207, 50.0888] },
	{ names: ['al khobar', 'khobar', 'الخبر'], center: [26.2794, 50.2083] },
	{ names: ['manama', 'المنامة'], center: [26.2285, 50.586] },
	{ names: ['doha', 'الدوحة'], center: [25.2854, 51.531] },
	{ names: ['kuwait city', 'الكويت', 'مدينة الكويت'], center: [29.3759, 47.9774] },
	{ names: ['abu dhabi', 'أبوظبي', 'أبو ظبي'], center: [24.4539, 54.3773] },
	{ names: ['dubai', 'دبي'], center: [25.2048, 55.2708] },
	{ names: ['muscat', 'مسقط'], center: [23.588, 58.3829] }
];

/** @param {string} name */
const normalize = (name) => name.trim().toLowerCase().replace(/\s+/g, ' ');

/**
 * @param {string|null|undefined} name What the owner typed. Matched whole, not
 *   as a prefix, so "Ri" does not jump the map while they are still typing.
 * @returns {[number, number] | null}
 */
export function cityCenter(name) {
	if (!name) return null;
	const wanted = normalize(name);
	return CITIES.find((city) => city.names.includes(wanted))?.center ?? null;
}
