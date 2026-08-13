import type { Handle } from '@sveltejs/kit';
import { defaultLocale, dirFor, isSupportedLocale } from '$lib/i18n';

const LOCALE_COOKIE = 'locale';

export const handle: Handle = async ({ event, resolve }) => {
	const cookieLocale = event.cookies.get(LOCALE_COOKIE);
	const headerLocale = event.request.headers
		.get('accept-language')
		?.split(',')[0]
		?.split('-')[0];

	const locale = isSupportedLocale(cookieLocale)
		? cookieLocale
		: isSupportedLocale(headerLocale)
			? headerLocale
			: defaultLocale;

	event.locals.locale = locale;

	return resolve(event, {
		// Reads event.locals.locale (not the `locale` const above) so a later
		// load function — e.g. +layout.server.ts applying a `?locale=` switch —
		// can still affect the html lang/dir before this streams out.
		transformPageChunk: ({ html }) =>
			html
				.replace('%lang%', event.locals.locale)
				.replace('%dir%', dirFor(event.locals.locale))
	});
};
