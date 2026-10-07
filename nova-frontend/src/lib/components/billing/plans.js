import { t, m, intlLocale } from '$lib/i18n/index.svelte.js';
/**
 * How the billing page talks about plans: names, who each is for, feature
 * labels, and the dates of a billing period. The prices and limits
 * themselves always come from the API (`GET /billing/plans`); nothing here
 * restates a number.
 */

/** @type {import('../../api/billing.js').PlanTier[]} */
export const TIER_ORDER = ['solo', 'studio', 'chain'];

/** @type {Record<string, { name: string, tagline: string, recommended?: boolean }>} */
export const PLAN_COPY = {
	solo: { name: m('Solo'), tagline: m('For independent stylists and therapists.') },
	studio: {
		name: m('Studio'),
		tagline: m('For salons, spas and clinics with a team.'),
		recommended: true
	},
	chain: { name: m('Chain'), tagline: m('For groups running several branches.') }
};

/** @param {string} tier */
export const planName = (tier) => t(PLAN_COPY[tier]?.name ?? tier);

/** @param {string} tier */
export const planTagline = (tier) => (PLAN_COPY[tier] ? t(PLAN_COPY[tier].tagline) : '');

/** `included_features` keys (billing/domain.py `PLANS`), as a salon reads them. */
const FEATURE_LABELS = {
	marketplace_profile: m('Listing on the NOVA marketplace'),
	calendar: m('Calendar and online booking'),
	queue_and_tickets: m('Walk-in queue and tickets'),
	ai_booking_agent: m('AI booking assistant'),
	ai_support_agent: m('AI customer support'),
	ai_insights_agent: m('AI business insights'),
	ai_retention_campaigns: m('AI win-back campaigns'),
	pos_and_product_sales: m('Point of sale and product sales'),
	cross_location_reporting: m('Reporting across branches'),
	api_access: m('API access')
};

/** @param {string} feature */
export function featureLabel(feature) {
	const known = /** @type {Record<string, string>} */ (FEATURE_LABELS)[feature];
	if (known) return t(known);
	const words = feature.replaceAll('_', ' ');
	return words.charAt(0).toUpperCase() + words.slice(1);
}

/** @param {string} tier */
export const tierRank = (tier) => TIER_ORDER.indexOf(/** @type {any} */ (tier));

/**
 * A billing period is half-open (`BillingPeriod`): `current_period_end` is
 * the first day of the next one. The last day the plan covers is the day
 * before it.
 * @param {string} periodEnd
 */
export function lastDayOf(periodEnd) {
	return new Date(Date.parse(`${periodEnd}T00:00:00Z`) - 864e5).toISOString().slice(0, 10);
}

/**
 * How far through its period a subscription is, 0–1.
 * @param {string} start @param {string} end @param {Date} [now]
 */
export function periodProgress(start, end, now = new Date()) {
	const a = Date.parse(`${start}T00:00:00Z`);
	const b = Date.parse(`${end}T00:00:00Z`);
	if (!(b > a)) return 0;
	return Math.min(1, Math.max(0, (now.getTime() - a) / (b - a)));
}

/** Whole days until `end`. @param {string} end @param {Date} [now] */
export function daysLeft(end, now = new Date()) {
	return Math.max(0, Math.ceil((Date.parse(`${end}T00:00:00Z`) - now.getTime()) / 864e5));
}

/**
 * A plain date (`YYYY-MM-DD`) as a calendar date. Formatted in UTC, the zone
 * it was written in, so it can never slip a day.
 * @param {string|null|undefined} day
 * @param {{ year?: boolean }} [options]
 */
export function formatDay(day, { year = true } = {}) {
	if (!day) return '—';
	return new Intl.DateTimeFormat(intlLocale(), {
		day: 'numeric',
		month: 'short',
		...(year ? { year: 'numeric' } : {}),
		timeZone: 'UTC'
	}).format(Date.parse(`${day.slice(0, 10)}T00:00:00Z`));
}

/**
 * A period as one phrase: "Sep 2026" for a whole month, else a range.
 * @param {string} start @param {string} end half-open
 */
export function formatPeriod(start, end) {
	const last = lastDayOf(end);
	const s = new Date(`${start}T00:00:00Z`);
	const e = new Date(`${last}T00:00:00Z`);
	const wholeMonth =
		s.getUTCDate() === 1 &&
		s.getUTCMonth() === e.getUTCMonth() &&
		new Date(Date.parse(`${end}T00:00:00Z`)).getUTCDate() === 1;
	if (wholeMonth) {
		return new Intl.DateTimeFormat(intlLocale(), {
			month: 'long',
			year: 'numeric',
			timeZone: 'UTC'
		}).format(s);
	}
	return `${formatDay(start, { year: false })} – ${formatDay(last)}`;
}

/**
 * A price as a salon reads a price list: whole riyals without ".00",
 * anything with fils in full.
 * @param {string|number|null|undefined} amount
 * @param {string} [currency]
 */
export function formatPrice(amount, currency = 'SAR') {
	const value = Number(amount ?? 0);
	return new Intl.NumberFormat(intlLocale(), {
		style: 'currency',
		currency,
		minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
		maximumFractionDigits: 2
	}).format(value);
}
