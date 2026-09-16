/**
 * Money formatting. Amounts arrive from the API as `Decimal`, serialised as a
 * JSON string or number — always parse through here rather than trusting the
 * wire type, and never do arithmetic on the result: it's for display only.
 */

const FORMATTER_CACHE = new Map();

/** @param {'en'|'ar'} locale @param {string} currency */
function formatterFor(locale, currency) {
	const key = `${locale}:${currency}`;
	let formatter = FORMATTER_CACHE.get(key);
	if (!formatter) {
		formatter = new Intl.NumberFormat(locale === 'ar' ? 'ar-SA' : 'en-US', {
			style: 'currency',
			currency,
			currencyDisplay: 'symbol'
		});
		FORMATTER_CACHE.set(key, formatter);
	}
	return formatter;
}

/**
 * @param {string|number|null|undefined} amount
 * @param {string} [currency]
 * @param {'en'|'ar'} [locale]
 */
export function formatMoney(amount, currency = 'SAR', locale = 'en') {
	if (amount === null || amount === undefined) return '—';
	const value = typeof amount === 'string' ? Number(amount) : amount;
	if (!Number.isFinite(value)) return '—';
	try {
		return formatterFor(locale, currency).format(value);
	} catch {
		// An unrecognised currency code — fall back rather than throwing.
		return `${value.toFixed(2)} ${currency}`;
	}
}

/** @param {string|number|null|undefined} value @param {{ locale?: 'en'|'ar', fractionDigits?: number }} [options] */
export function formatPercent(value, { locale = 'en', fractionDigits = 1 } = {}) {
	if (value === null || value === undefined) return '—';
	const number = typeof value === 'string' ? Number(value) : value;
	if (!Number.isFinite(number)) return '—';
	return new Intl.NumberFormat(locale === 'ar' ? 'ar-SA' : 'en-US', {
		style: 'percent',
		minimumFractionDigits: 0,
		maximumFractionDigits: fractionDigits
	}).format(number / 100);
}
