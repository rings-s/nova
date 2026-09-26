/**
 * Chooses each request's language before anything renders, so the HTML
 * arrives with the right `lang` and `dir` and no flash of the wrong one.
 *
 * The `nova_locale` cookie (set by the language switch) wins. Without it, a
 * browser that prefers Arabic over English gets Arabic.
 */
import { LOCALE_COOKIE, dirFor, isLocale } from '$lib/i18n/index.svelte.js';

/** @param {string|null} header @returns {'en'|'ar'} */
function fromAcceptLanguage(header) {
	for (const part of (header ?? '').split(',')) {
		const tag = part.split(';')[0].trim().toLowerCase();
		if (tag.startsWith('ar')) return 'ar';
		if (tag.startsWith('en')) return 'en';
	}
	return 'en';
}

/** @type {import('@sveltejs/kit').Handle} */
export async function handle({ event, resolve }) {
	const cookie = event.cookies.get(LOCALE_COOKIE);
	const locale = isLocale(cookie)
		? cookie
		: fromAcceptLanguage(event.request.headers.get('accept-language'));
	event.locals.locale = locale;

	return resolve(event, {
		transformPageChunk: ({ html }) =>
			html.replace('%nova.lang%', locale).replace('%nova.dir%', dirFor(locale))
	});
}
