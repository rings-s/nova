/**
 * English and Arabic for the whole app, without a library.
 *
 * Messages are written in English where they are used and looked up in
 * `ar.js` when the locale is Arabic, gettext-style: the English text is the
 * key. Call sites stay readable, English needs no dictionary, and
 * `npm run i18n:check` fails when a string has no Arabic translation.
 *
 *   t('Book now')
 *   t('Hello, {name}', { name })
 *   tp(count, '{count} booking', '{count} bookings')   // Arabic has six plural forms
 *   m('Revenue')   // marks a string kept in a JS constant, translated later by t()
 *
 * `t` reads the locale from reactive state, so markup and `$derived`s that
 * call it update when the language changes. The locale comes from the
 * `nova_locale` cookie, set by `setLocale`, so a server-rendered page is
 * already in the right language and direction (`hooks.server.js`).
 */
import { AR } from './ar.js';

/** @typedef {'en'|'ar'} Locale */

export const LOCALES = /** @type {const} */ (['en', 'ar']);
export const LOCALE_COOKIE = 'nova_locale';

export const i18n = $state({ locale: /** @type {Locale} */ ('en') });

/** @param {unknown} value @returns {value is Locale} */
export function isLocale(value) {
	return value === 'en' || value === 'ar';
}

/** @param {Locale} [locale] */
export function dirFor(locale = i18n.locale) {
	return locale === 'ar' ? 'rtl' : 'ltr';
}

/**
 * The BCP 47 tag for `Intl`. Arabic keeps Western digits (0-9), as Saudi
 * banking, telecom and delivery apps do, so prices, times and phone numbers
 * read the same in both languages and copy cleanly.
 * @param {Locale} [locale]
 */
export function intlLocale(locale = i18n.locale) {
	return locale === 'ar' ? 'ar-SA-u-nu-latn' : 'en-US';
}

/**
 * Switches language, remembers it, and flips the page direction.
 * @param {Locale} locale
 */
export function setLocale(locale) {
	i18n.locale = locale;
	if (typeof document === 'undefined') return;
	document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=31536000; samesite=lax`;
	document.documentElement.lang = locale;
	document.documentElement.dir = dirFor(locale);
}

/** @param {string} text @param {Record<string, unknown>} [params] */
function fill(text, params) {
	if (!params) return text;
	return text.replace(/\{(\w+)\}/g, (whole, name) =>
		name in params ? String(params[name] ?? '') : whole
	);
}

/**
 * The message in the active language.
 * @param {string} message English text, which is also the lookup key.
 * @param {Record<string, unknown>} [params] Values for `{name}` placeholders.
 * @returns {string}
 */
export function t(message, params) {
	if (i18n.locale === 'ar') {
		const translated = AR[message];
		if (typeof translated === 'string') return fill(translated, params);
	}
	return fill(message, params);
}

const PLURAL_RULES = {
	en: new Intl.PluralRules('en-US'),
	ar: new Intl.PluralRules('ar-SA')
};

/**
 * A message that depends on a count. English has one and other; Arabic has
 * zero, one, two, few, many and other, given in `ar.js` as an object keyed by
 * `Intl.PluralRules` category under the English plural form.
 * @param {number} count
 * @param {string} one English singular, e.g. '{count} booking'
 * @param {string} other English plural, e.g. '{count} bookings' (the lookup key)
 * @param {Record<string, unknown>} [params]
 */
export function tp(count, one, other, params) {
	const values = { count, ...params };
	if (i18n.locale === 'ar') {
		const forms = AR[other];
		if (forms && typeof forms === 'object') {
			const category = PLURAL_RULES.ar.select(count);
			const text = forms[category] ?? forms.other;
			if (text) return fill(text, values);
		}
		if (typeof forms === 'string') return fill(forms, values);
	}
	return fill(PLURAL_RULES.en.select(count) === 'one' ? one : other, values);
}

/**
 * Marks a string for translation where it is defined, in a constant that is
 * rendered later through `t()`. Returns it unchanged; it exists so the check
 * script can find it.
 * @template {string} T
 * @param {T} message
 * @returns {T}
 */
export function m(message) {
	return message;
}
