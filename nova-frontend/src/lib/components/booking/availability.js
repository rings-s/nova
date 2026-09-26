/**
 * The slot data behind every availability view (SlotPicker, the full-page
 * booking calendar and its time modal): one fetch that works against either
 * the staff `getAvailability` (booking.js) or the public
 * `getPublicAvailability` (discovery.js), and the day/period arithmetic the
 * views share.
 *
 * Day keys are `YYYY-MM-DD` in the salon's own clock (`dateKey`,
 * datetime.js). Calendar layout is plain `{year, month, day}` arithmetic,
 * never a `Date` formatted through a timezone, so a cell cannot land on the
 * wrong day for a viewer far from Asia/Riyadh.
 */
import { getAvailability } from '../../api/booking.js';
import { getPublicAvailability } from '../../api/discovery.js';
import { dateKey, DEFAULT_TIMEZONE } from '../../utils/datetime.js';

/** @typedef {import('../../api/booking.js').AvailableSlot|import('../../api/discovery.js').PublicSlot} Slot */

/**
 * @param {{
 *   source?: 'tenant'|'public',
 *   tenantId?: string,
 *   providerId?: string,
 *   slug?: string,
 *   serviceId: string,
 *   dateFrom: string,
 *   dateTo: string
 * }} params
 * @returns {Promise<Slot[]>}
 */
export function fetchSlots({
	source = 'tenant',
	tenantId,
	providerId,
	slug,
	serviceId,
	dateFrom,
	dateTo
}) {
	// `slug` (public) and `tenantId` (tenant) are each required only for the
	// branch that uses them — the caller picks one via `source`.
	return source === 'public'
		? getPublicAvailability(/** @type {string} */ (slug), serviceId, { dateFrom, dateTo }).then(
				(r) => r.slots
			)
		: getAvailability(/** @type {string} */ (tenantId), {
				providerId: /** @type {string} */ (providerId),
				serviceId,
				dateFrom,
				dateTo
			}).then((r) => r.items);
}

/**
 * Slots grouped by the salon-clock day they start on, each day in time order.
 * @param {Slot[]} slots @returns {Map<string, Slot[]>}
 */
export function groupSlotsByDay(slots) {
	/** @type {Map<string, Slot[]>} */
	const groups = new Map();
	const sorted = [...slots].sort((a, b) => a.starts_at.localeCompare(b.starts_at));
	for (const slot of sorted) {
		const key = dateKey(slot.starts_at);
		const day = groups.get(key);
		if (day) day.push(slot);
		else groups.set(key, [slot]);
	}
	return groups;
}

export const PERIOD_ORDER = /** @type {const} */ (['morning', 'afternoon', 'evening']);

/** @typedef {typeof PERIOD_ORDER[number]} Period */

/** @param {string} iso @returns {Period} */
export function periodOf(iso) {
	const hour = Number(
		new Intl.DateTimeFormat('en-US', {
			timeZone: DEFAULT_TIMEZONE,
			hour: 'numeric',
			hour12: false
		}).format(new Date(iso))
	);
	if (hour < 12) return 'morning';
	if (hour < 17) return 'afternoon';
	return 'evening';
}

/** @param {Slot[]} slots @returns {Record<Period, Slot[]>} */
export function slotsByPeriod(slots) {
	/** @type {Record<Period, Slot[]>} */
	const buckets = { morning: [], afternoon: [], evening: [] };
	for (const slot of slots) buckets[periodOf(slot.starts_at)].push(slot);
	return buckets;
}

/** @param {number} year @param {number} month 0-indexed */
export function monthKey(year, month) {
	return `${year}-${String(month + 1).padStart(2, '0')}`;
}

/**
 * Every `{year, month}` (0-indexed month) from the month of `fromKey` to the
 * month of `toKey`, inclusive.
 * @param {string} fromKey @param {string} toKey
 * @returns {{ year: number, month: number }[]}
 */
export function monthsBetween(fromKey, toKey) {
	if (!fromKey || !toKey) return [];
	const [fy, fm] = fromKey.split('-').map(Number);
	const [ty, tm] = toKey.split('-').map(Number);
	const months = [];
	for (let total = fy * 12 + fm - 1; total <= ty * 12 + tm - 1; total++) {
		months.push({ year: Math.floor(total / 12), month: total % 12 });
	}
	return months;
}

/**
 * The day cells of one month, Monday-first (as the rest of the app:
 * booking.js's WorkingWindow, the schedule editor), with `null` for the
 * leading blanks.
 * @param {number} year @param {number} month 0-indexed
 * @returns {({ key: string, day: number }|null)[]}
 */
export function monthCells(year, month) {
	const daysInMonth = new Date(year, month + 1, 0).getDate();
	// getDay() is Sunday=0..Saturday=6; rotate to Monday=0..Sunday=6.
	const leadingBlanks = (new Date(year, month, 1).getDay() + 6) % 7;
	/** @type {({ key: string, day: number }|null)[]} */
	const cells = Array.from({ length: leadingBlanks }, () => null);
	for (let day = 1; day <= daysInMonth; day++) {
		cells.push({ key: `${monthKey(year, month)}-${String(day).padStart(2, '0')}`, day });
	}
	return cells;
}

/**
 * A day key as a `Date` at noon UTC — format it with `timeZone: 'UTC'` and it
 * names the same calendar day for every viewer.
 * @param {string} key
 */
export function dayKeyToDate(key) {
	return new Date(`${key}T12:00:00Z`);
}
