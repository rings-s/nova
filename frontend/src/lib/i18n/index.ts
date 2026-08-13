import ar from './ar.json';
import en from './en.json';

/**
 * Hand-rolled i18n rather than a compiler-based library (e.g. Paraglide):
 * only two locales are in scope today, and this keeps the scaffold free of an
 * extra build-time dependency. Revisit if locale count or message volume grows.
 * See docs/frontend/i18n-rtl.md.
 */

export const locales = ['en', 'ar'] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = 'en';

const dictionaries: Record<Locale, Record<string, string>> = { en, ar };

export function isSupportedLocale(value: string | null | undefined): value is Locale {
	return !!value && (locales as readonly string[]).includes(value);
}

export function isRtl(locale: Locale): boolean {
	return locale === 'ar';
}

export function dirFor(locale: Locale): 'ltr' | 'rtl' {
	return isRtl(locale) ? 'rtl' : 'ltr';
}

export type MessageKey = keyof typeof en;

export function t(locale: Locale, key: MessageKey): string {
	return dictionaries[locale][key] ?? dictionaries[defaultLocale][key] ?? key;
}
