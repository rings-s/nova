/**
 * NOVA stores bilingual text as `name_en`/`name_ar` column pairs (ADR-0004,
 * both required). This picks the right one for the active locale, with a
 * fallback so a missing translation never renders blank.
 */
import { i18n } from '../i18n/index.svelte.js';

/**
 * @param {Record<string, unknown>} record
 * @param {string} field Base field name, e.g. `"name"` for `name_en`/`name_ar`.
 * @param {'en'|'ar'} [locale]
 */
export function pickBilingual(record, field, locale = i18n.locale) {
	if (!record) return '';
	const primary = record[`${field}_${locale}`];
	const fallback = locale === 'ar' ? record[`${field}_en`] : record[`${field}_ar`];
	return /** @type {string} */ (primary ?? fallback ?? '');
}

/** Text direction for the active locale, for a `dir` attribute. @param {'en'|'ar'} locale */
export function directionFor(locale) {
	return locale === 'ar' ? 'rtl' : 'ltr';
}
