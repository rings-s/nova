import { isSupportedLocale } from '$lib/i18n';
import type { LayoutServerLoad } from './$types';

const LOCALE_COOKIE = 'locale';

export const load: LayoutServerLoad = ({ locals, url, cookies }) => {
	const requestedLocale = url.searchParams.get('locale');
	if (isSupportedLocale(requestedLocale) && requestedLocale !== locals.locale) {
		locals.locale = requestedLocale;
		cookies.set(LOCALE_COOKIE, requestedLocale, { path: '/', maxAge: 60 * 60 * 24 * 365 });
	}

	return { locale: locals.locale };
};
