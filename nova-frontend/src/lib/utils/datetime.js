/**
 * Date/time formatting. The backend's default timezone is Asia/Riyadh
 * (core/values.Money and booking's own scheduling both assume it) — every
 * formatter here defaults to it so a slot at "09:00" reads the same in the
 * salon's own time regardless of the viewer's device.
 */

export const DEFAULT_TIMEZONE = 'Asia/Riyadh';

/** @param {'en'|'ar'} locale */
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

/**
 * "in 12 minutes" / "3 days ago" — for holds, waits, and expiries.
 * @param {string|Date} value @param {'en'|'ar'} [locale]
 */
export function formatRelative(value, locale = 'en') {
	const date = value instanceof Date ? value : new Date(value);
	if (Number.isNaN(date.getTime())) return '—';
	const diffSeconds = Math.round((date.getTime() - Date.now()) / 1000);
	const rtf = new Intl.RelativeTimeFormat(localeTag(locale), { numeric: 'auto' });
	const absSeconds = Math.abs(diffSeconds);

	if (absSeconds < 60) return rtf.format(diffSeconds, 'second');
	if (absSeconds < 3600) return rtf.format(Math.round(diffSeconds / 60), 'minute');
	if (absSeconds < 86400) return rtf.format(Math.round(diffSeconds / 3600), 'hour');
	return rtf.format(Math.round(diffSeconds / 86400), 'day');
}

/** Minutes-from-midnight (booking's `WorkingWindow` shape) as `HH:MM`. @param {number} minutes */
export function formatMinutesOfDay(minutes) {
	const wrapped = ((minutes % 1440) + 1440) % 1440;
	const hours = Math.floor(wrapped / 60)
		.toString()
		.padStart(2, '0');
	const mins = (wrapped % 60).toString().padStart(2, '0');
	return `${hours}:${mins}`;
}

/**
 * `HH:MM` (or `HH:MM:SS`) back to minutes-from-midnight, for schedule forms.
 * @param {string} hhmm
 */
export function parseMinutesOfDay(hhmm) {
	const [hours, minutes] = hhmm.split(':').map(Number);
	return hours * 60 + (minutes || 0);
}

/**
 * An instant's calendar date, as `YYYY-MM-DD` in a timezone — for grouping
 * or comparing instants by day (string comparison sorts correctly). `en-CA`
 * is a locale that happens to format dates this way; the locale itself is
 * otherwise irrelevant here.
 * @param {string|Date} value @param {{ timeZone?: string }} [options]
 */
export function dateKey(value, { timeZone = DEFAULT_TIMEZONE } = {}) {
	const date = value instanceof Date ? value : new Date(value);
	if (Number.isNaN(date.getTime())) return '';
	return new Intl.DateTimeFormat('en-CA', {
		timeZone,
		year: 'numeric',
		month: '2-digit',
		day: '2-digit'
	}).format(date);
}

export const WEEKDAY_LABELS = {
	en: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
	ar: ['الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']
};

/** @param {number} weekday Monday = 0. @param {'en'|'ar'} [locale] */
export function weekdayLabel(weekday, locale = 'en') {
	return WEEKDAY_LABELS[locale]?.[weekday] ?? WEEKDAY_LABELS.en[weekday] ?? '';
}

/** Calendar column headers — a compact calendar has no room for full names. */
export const SHORT_WEEKDAY_LABELS = {
	en: ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'],
	ar: ['ن', 'ث', 'ر', 'خ', 'ج', 'س', 'ح']
};

/** @param {number} weekday Monday = 0. @param {'en'|'ar'} [locale] */
export function shortWeekdayLabel(weekday, locale = 'en') {
	return SHORT_WEEKDAY_LABELS[locale]?.[weekday] ?? SHORT_WEEKDAY_LABELS.en[weekday] ?? '';
}
