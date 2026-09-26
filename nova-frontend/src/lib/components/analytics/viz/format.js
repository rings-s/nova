import { t, i18n, intlLocale } from '$lib/i18n/index.svelte.js';
/**
 * Number and label formatting shared by the analytics chart kit. Values keep
 * their unit end to end (`chartData.js::Unit`), so a tooltip, an axis tick
 * and a table cell for the same number always agree.
 */

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** @param {'en'|'ar'} locale */
const tag = (locale) => intlLocale(locale);

/**
 * A value in full, for tooltips, direct labels and tables.
 * @param {number|null|undefined} value
 * @param {import('../../../utils/chartData.js').Unit} unit
 * @param {{ currency?: string, locale?: 'en'|'ar' }} [options]
 */
export function formatValue(value, unit, { currency = 'SAR', locale = i18n.locale } = {}) {
	if (value === null || value === undefined || Number.isNaN(value)) return '—';
	switch (unit) {
		case 'money':
			return new Intl.NumberFormat(tag(locale), {
				style: 'currency',
				currency,
				maximumFractionDigits: Math.abs(value) >= 1000 ? 0 : 2
			}).format(value);
		case 'percent':
			return `${new Intl.NumberFormat(tag(locale), { maximumFractionDigits: 1 }).format(value)}%`;
		case 'minutes':
			return t('{minutes} min', {
				minutes: new Intl.NumberFormat(tag(locale), { maximumFractionDigits: 1 }).format(value)
			});
		default:
			return new Intl.NumberFormat(tag(locale), { maximumFractionDigits: 1 }).format(value);
	}
}

/**
 * A short value for an axis tick: compact, no currency code (the chart's
 * title names it), so ticks stay narrow.
 * @param {number} value
 * @param {import('../../../utils/chartData.js').Unit} unit
 * @param {'en'|'ar'} [locale]
 */
export function formatTick(value, unit, locale = i18n.locale) {
	const number = new Intl.NumberFormat(tag(locale), {
		notation: 'compact',
		maximumFractionDigits: 1
	}).format(value);
	return unit === 'percent' ? `${number}%` : number;
}

/**
 * A category label: ISO dates as a short day, anything else as given.
 * @param {string} category
 * @param {{ locale?: 'en'|'ar', long?: boolean }} [options]
 */
export function formatCategory(category, { locale = i18n.locale, long = false } = {}) {
	if (!ISO_DATE_RE.test(category)) return category;
	const [y, m, d] = category.split('-').map(Number);
	return new Intl.DateTimeFormat(tag(locale), {
		day: 'numeric',
		month: 'short',
		...(long ? { weekday: 'short', year: 'numeric' } : {}),
		timeZone: 'UTC'
	}).format(Date.UTC(y, m - 1, d));
}

/**
 * A month (for cohorts, which the backend names by their first day).
 * @param {string} category
 * @param {'en'|'ar'} [locale]
 */
export function formatMonth(category, locale = i18n.locale) {
	if (!ISO_DATE_RE.test(category)) return category;
	const [y, m] = category.split('-').map(Number);
	return new Intl.DateTimeFormat(tag(locale), {
		month: 'short',
		year: 'numeric',
		timeZone: 'UTC'
	}).format(Date.UTC(y, m - 1, 1));
}

/**
 * Every n-th category, so axis labels keep at least `minGap` px apart.
 * @param {number} count @param {number} width @param {number} [minGap]
 */
export function labelStep(count, width, minGap = 64) {
	if (count <= 1 || width <= 0) return 1;
	return Math.max(1, Math.ceil(count / Math.max(1, Math.floor(width / minGap))));
}

/**
 * A bar with only its data end rounded: the end away from the baseline gets
 * radius `r`, the base stays square so every bar sits flush on the axis.
 * @param {number} x @param {number} y @param {number} w @param {number} h
 * @param {number} r @param {'top'|'end'|'none'} round
 */
export function barPath(x, y, w, h, r, round) {
	if (w <= 0 || h <= 0) return '';
	if (round === 'none') return `M${x},${y}h${w}v${h}h${-w}Z`;
	if (round === 'top') {
		const k = Math.min(r, w / 2, h);
		return `M${x},${y + h}V${y + k}Q${x},${y} ${x + k},${y}H${x + w - k}Q${x + w},${y} ${x + w},${y + k}V${y + h}Z`;
	}
	const k = Math.min(r, h / 2, w);
	return `M${x},${y}H${x + w - k}Q${x + w},${y} ${x + w},${y + k}V${y + h - k}Q${x + w},${y + h} ${x + w - k},${y + h}H${x}Z`;
}
