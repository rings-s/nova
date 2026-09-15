/**
 * Date/time formatting. The backend's default timezone is Asia/Riyadh
 * (core/values.Money and booking's own scheduling both assume it) — every
 * formatter here defaults to it so a slot at "09:00" reads the same in the
 * salon's own time regardless of the viewer's device.
 */

const DEFAULT_TIMEZONE = 'Asia/Riyadh';

function localeTag(locale) {
	return locale === 'ar' ? 'ar-SA' : 'en-US';
}

/** @param {string|Date} value @param {'en'|'ar'} [locale] */
export function formatDateTime(value, locale = 'en', { timeZone = DEFAULT_TIMEZONE } = {}) {
	const date = value instanceof Date ? value : new Date(value);
	if (Number.isNaN(date.getTime())) return '—';
	return new Intl.DateTimeFormat(localeTag(locale), {
		timeZone,
		dateStyle: 'medium',
		timeStyle: 'short'
	}).format(date);
}

/** @param {string|Date} value @param {'en'|'ar'} [locale] */
export function formatDate(value, locale = 'en', { timeZone = DEFAULT_TIMEZONE } = {}) {
	const date = value instanceof Date ? value : new Date(value);
	if (Number.isNaN(date.getTime())) return '—';
	return new Intl.DateTimeFormat(localeTag(locale), { timeZone, dateStyle: 'medium' }).format(date);
}

/** @param {string|Date} value @param {'en'|'ar'} [locale] */
export function formatTime(value, locale = 'en', { timeZone = DEFAULT_TIMEZONE } = {}) {
	const date = value instanceof Date ? value : new Date(value);
	if (Number.isNaN(date.getTime())) return '—';
	return new Intl.DateTimeFormat(localeTag(locale), { timeZone, timeStyle: 'short' }).format(date);
}

/** "in 12 minutes" / "3 days ago" — for holds, waits, and expiries. */
export function formatRelative(value, locale = 'en') {
	const date = value instanceof Date ? value : new Date(value);
	if (Number.isNaN(date.getTime())) return '—';
	const diffSeconds = Math.round((date.getTime() - Date.now()) / 1000);
	const rtf = new Intl.RelativeTimeFormat(localeTag(locale), { numeric: 'auto' });

	const thresholds = [
		[60, 'second'],
		[60 * 60, 'minute'],
		[60 * 60 * 24, 'hour'],
		[60 * 60 * 24 * 30, 'day']
	];
	let unit = 'second';
	let divisor = 1;
	for (const [limit, unitName] of thresholds) {
		if (Math.abs(diffSeconds) < limit) {
			unit = unitName;
			break;
		}
		divisor = limit;
	}
	const value_ =
		unit === 'second' ? diffSeconds : Math.round(diffSeconds / (divisor || 1));
	return rtf.format(value_, /** @type {Intl.RelativeTimeFormatUnit} */ (unit));
}

/** Minutes-from-midnight (booking's `WorkingWindow` shape) as `HH:MM`. */
export function formatMinutesOfDay(minutes) {
	const wrapped = ((minutes % 1440) + 1440) % 1440;
	const hours = Math.floor(wrapped / 60)
		.toString()
		.padStart(2, '0');
	const mins = (wrapped % 60).toString().padStart(2, '0');
	return `${hours}:${mins}`;
}

/** `HH:MM` (or `HH:MM:SS`) back to minutes-from-midnight, for schedule forms. */
export function parseMinutesOfDay(hhmm) {
	const [hours, minutes] = hhmm.split(':').map(Number);
	return hours * 60 + (minutes || 0);
}

export const WEEKDAY_LABELS = {
	en: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
	ar: ['الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']
};

/** @param {number} weekday Monday = 0. @param {'en'|'ar'} [locale] */
export function weekdayLabel(weekday, locale = 'en') {
	return WEEKDAY_LABELS[locale]?.[weekday] ?? WEEKDAY_LABELS.en[weekday] ?? '';
}
