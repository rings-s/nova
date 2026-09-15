/**
 * analytics — nova_backend/app/modules/analytics/router.py
 *
 * A business's own numbers, and the Plotly charts that show them. Gated by
 * `view_analytics` throughout; the financial summary also needs `view_financials`.
 */
import { http, tenantPath } from './client.js';

/**
 * @typedef {'day'|'week'|'month'} Granularity
 * @typedef {'service'|'provider'|'source'|'location'} Dimension
 * @typedef {'bookings'|'revenue'} ForecastMetric
 */

/**
 * @typedef {Object} ReportWindow
 * @property {string} date_from
 * @property {string} date_to
 * @property {string} timezone
 * @property {number} days
 */

/**
 * @typedef {Object} Kpi
 * @property {string} metric
 * @property {string|null} value Null exactly when `suppressed`.
 * @property {string} unit
 * @property {number} sample_size
 * @property {boolean} suppressed Too small a sample to report.
 */

/**
 * @typedef {Object} Overview
 * @property {string} business_id
 * @property {ReportWindow} window
 * @property {string} currency
 * @property {number} excluded_rows Left out for being in another currency.
 * @property {Kpi[]} kpis
 */

/**
 * @typedef {Object} BreakdownRow
 * @property {Dimension} dimension
 * @property {string} key
 * @property {string} label Localised per the `locale` param.
 * @property {string} label_en
 * @property {string} label_ar
 * @property {number} bookings
 * @property {number} completed
 * @property {string} revenue
 * @property {string|null} share_of_revenue
 */

/**
 * @typedef {Object} ChartCatalogEntry
 * @property {string} chart_id
 * @property {string} kind
 * @property {string} title_en
 * @property {string} title_ar
 * @property {string} question_en
 * @property {string} question_ar
 * @property {string|null} required_feature
 */

/**
 * @typedef {Object} Chart
 * @property {string} chart_id
 * @property {string} kind
 * @property {string} title
 * @property {string} description
 * @property {string} locale
 * @property {string} business_id
 * @property {string} date_from
 * @property {string} date_to
 * @property {Granularity|null} granularity
 * @property {string} currency
 * @property {number} data_points
 * @property {string} generated_at
 * @property {Record<string, unknown>} figure Plotly figure JSON — hand to plotly.js as-is.
 */

/**
 * @typedef {Object} ForecastPoint
 * @property {string} week_start
 * @property {string} value
 * @property {string|null} lower
 * @property {string|null} upper
 * @property {boolean} is_forecast
 */

/**
 * @typedef {Object} Forecast
 * @property {string} business_id
 * @property {ForecastMetric} metric
 * @property {string} currency
 * @property {string} method Always `"linear_trend"` — never a promise.
 * @property {number} history_weeks
 * @property {string} slope_per_week
 * @property {ForecastPoint[]} points
 */

/**
 * @typedef {Object} FinancialSummary
 * @property {string} business_id
 * @property {ReportWindow} window
 * @property {string} currency
 * @property {string} revenue
 * @property {string} collected
 * @property {string} refunded
 * @property {string} commission_accrued
 * @property {string} commission_reversed
 * @property {string} payouts_collected
 * @property {string} payouts_processing_fees
 * @property {string} payouts_commission_netted
 * @property {string} payouts_net
 * @property {string} invoiced_subscription
 * @property {string} invoiced_commission
 * @property {string} invoiced_processing
 * @property {string} invoiced_vat
 * @property {string} invoiced_total
 * @property {number} outstanding_invoices
 * @property {string} outstanding_total
 */

/** The chart catalog, with the plan feature each needs. @returns {Promise<{ items: ChartCatalogEntry[] }>} */
export function listCharts(tenantId) {
	return http.get(tenantPath(tenantId, '/analytics/charts'));
}

/**
 * One chart as Plotly JSON.
 * @returns {Promise<Chart>}
 */
export function getChart(
	tenantId,
	chartId,
	{ businessId, dateFrom = null, dateTo = null, granularity = null, locale = 'en' }
) {
	return http.get(tenantPath(tenantId, `/analytics/charts/${chartId}`), {
		query: { business_id: businessId, date_from: dateFrom, date_to: dateTo, granularity, locale }
	});
}

/** Every KPI, with a null value where the sample was too small to report. @returns {Promise<Overview>} */
export function getOverview(tenantId, businessId, { dateFrom = null, dateTo = null } = {}) {
	return http.get(tenantPath(tenantId, '/analytics/overview'), {
		query: { business_id: businessId, date_from: dateFrom, date_to: dateTo }
	});
}

/** Per service, provider, source, or (on Chain) branch. @returns {Promise<{ items: BreakdownRow[] }>} */
export function getBreakdown(
	tenantId,
	businessId,
	dimension,
	{ dateFrom = null, dateTo = null, locale = 'en' } = {}
) {
	return http.get(tenantPath(tenantId, '/analytics/breakdown'), {
		query: { business_id: businessId, dimension, date_from: dateFrom, date_to: dateTo, locale }
	});
}

/** A linear trend over complete weeks — never a promise. @returns {Promise<Forecast>} */
export function getForecast(
	tenantId,
	businessId,
	{ metric = 'bookings', horizonWeeks = 4 } = {}
) {
	return http.get(tenantPath(tenantId, '/analytics/forecast'), {
		query: { business_id: businessId, metric, horizon_weeks: horizonWeeks }
	});
}

/** The accountant's ledger for one window. Needs `view_financials` too. @returns {Promise<FinancialSummary>} */
export function getFinancialSummary(tenantId, businessId, { dateFrom = null, dateTo = null } = {}) {
	return http.get(tenantPath(tenantId, '/analytics/financial-summary'), {
		query: { business_id: businessId, date_from: dateFrom, date_to: dateTo }
	});
}
