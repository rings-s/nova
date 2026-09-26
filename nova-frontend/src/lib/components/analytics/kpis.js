import { t, m, i18n, intlLocale } from '$lib/i18n/index.svelte.js';
/**
 * What each overview KPI (`analytics/domain.py::MetricName`) means on screen:
 * its label, which way is good, and how its value and its change against the
 * previous window are written. Units are the backend's `KpiOut.unit`: count,
 * money (major units), ratio (0–1), hours, minutes.
 */

/**
 * @typedef {Object} KpiMeta
 * @property {string} label
 * @property {1|-1|0} better 1 when up is good, -1 when down is good, 0 when neither.
 * @property {string} [hint]
 */

/** @type {Record<string, KpiMeta>} */
export const KPI_META = {
	revenue: { label: m('Revenue'), better: 1, hint: m('Completed bookings') },
	average_ticket: { label: m('Average ticket'), better: 1 },
	collected: { label: m('Collected'), better: 1, hint: m('Paid online') },
	refunded: { label: m('Refunded'), better: -1 },
	prepaid_share: { label: m('Prepaid'), better: 1, hint: m('Of completed bookings') },
	bookings: { label: m('Bookings'), better: 1 },
	completed: { label: m('Completed'), better: 1 },
	cancelled: { label: m('Cancelled'), better: -1 },
	no_show: { label: m('No-shows'), better: -1 },
	completion_rate: { label: m('Completion rate'), better: 1 },
	cancellation_rate: { label: m('Cancellation rate'), better: -1 },
	no_show_rate: { label: m('No-show rate'), better: -1 },
	marketplace_share: { label: m('From NOVA marketplace'), better: 1 },
	median_lead_time_hours: { label: m('Booked ahead (median)'), better: 0 },
	unique_customers: { label: m('Customers'), better: 1 },
	new_customers: { label: m('New customers'), better: 1 },
	returning_customers: { label: m('Returning customers'), better: 1 },
	repeat_rate: { label: m('Repeat rate'), better: 1 },
	lapsed_customers: { label: m('Lapsed customers'), better: -1, hint: m('No visit in 90 days') },
	utilization: { label: m('Utilization'), better: 1, hint: m('Booked of scheduled hours') },
	walk_ins: { label: m('Walk-ins'), better: 1 },
	average_queue_wait_minutes: { label: m('Average wait'), better: -1 }
};

/** @param {string} metric */
export function kpiMeta(metric) {
	return KPI_META[metric] ?? { label: metric.replaceAll('_', ' '), better: 0 };
}

/**
 * A KPI value as text; null when there is none to show.
 * @param {import('../../api/analytics.js').Kpi|undefined} kpi
 * @param {{ currency?: string, locale?: 'en'|'ar', compact?: boolean }} [options]
 */
export function formatKpi(kpi, { currency = 'SAR', locale = i18n.locale, compact = false } = {}) {
	if (!kpi || kpi.suppressed || kpi.value === null) return null;
	const value = Number(kpi.value);
	const tag = intlLocale(locale);
	switch (kpi.unit) {
		case 'money':
			return new Intl.NumberFormat(tag, {
				style: 'currency',
				currency,
				notation: compact && Math.abs(value) >= 100_000 ? 'compact' : 'standard',
				maximumFractionDigits: Math.abs(value) >= 1000 ? 0 : 2
			}).format(value);
		case 'ratio':
			return new Intl.NumberFormat(tag, { style: 'percent', maximumFractionDigits: 1 }).format(
				value
			);
		case 'hours':
			return value >= 48
				? t('{n} days', {
						n: new Intl.NumberFormat(tag, { maximumFractionDigits: 1 }).format(value / 24)
					})
				: t('{n} h', { n: new Intl.NumberFormat(tag, { maximumFractionDigits: 1 }).format(value) });
		case 'minutes':
			return t('{minutes} min', {
				minutes: new Intl.NumberFormat(tag, { maximumFractionDigits: 1 }).format(value)
			});
		default:
			return new Intl.NumberFormat(tag).format(value);
	}
}

/**
 * The change from the previous window. Rates change in percentage points,
 * everything else by percent; a change from zero has no percent, so it is
 * reported as "new" rather than as an infinite rise.
 * @param {import('../../api/analytics.js').Kpi|undefined} current
 * @param {import('../../api/analytics.js').Kpi|undefined} previous
 * @returns {{ text: string, direction: 1|-1|0, tone: 'good'|'bad'|'neutral' }|null}
 */
export function kpiDelta(current, previous) {
	if (!current || !previous || current.value === null || previous.value === null) return null;
	if (current.suppressed || previous.suppressed) return null;
	const now = Number(current.value);
	const before = Number(previous.value);
	const diff = now - before;
	/** @type {1|-1|0} */
	const direction = Math.abs(diff) < 1e-9 ? 0 : diff > 0 ? 1 : -1;
	const better = kpiMeta(current.metric).better;
	const tone = direction === 0 || better === 0 ? 'neutral' : direction === better ? 'good' : 'bad';

	let text;
	if (current.unit === 'ratio') {
		text = t('{n} pts', { n: Math.abs(diff * 100).toFixed(1) });
	} else if (before === 0) {
		if (direction === 0) text = t('No change');
		else return { text: t('New'), direction, tone };
	} else {
		const pct = Math.abs((diff / before) * 100);
		text = `${pct >= 100 ? Math.round(pct) : pct.toFixed(1)}%`;
	}
	if (direction === 0) text = t('No change');
	return { text, direction, tone };
}
