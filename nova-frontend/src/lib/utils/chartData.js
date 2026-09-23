/**
 * Turns the Plotly figure JSON that `analytics.getChart` returns
 * (nova_backend/app/modules/analytics/charts.py — `data` traces plus `layout`)
 * into small chart models the analytics chart kit draws directly, so the
 * frontend never depends on plotly.js. Detection reads trace *structure*
 * (`type`, `orientation`, `fill`, `line.dash`) rather than trace names, since
 * names are localised (English or Arabic) and structure isn't.
 *
 * Colours come from the design system's validated chart tokens (layout.css).
 * The categorical order is fixed: never reorder it, cycle it or generate a
 * ninth hue here.
 */

/** Fixed categorical order — do not reorder or cycle past 8; fold a 9th series into "Other". */
export const CATEGORICAL_COLORS = [
	'var(--chart-series-1)',
	'var(--chart-series-2)',
	'var(--chart-series-3)',
	'var(--chart-series-4)',
	'var(--chart-series-5)',
	'var(--chart-series-6)',
	'var(--chart-series-7)',
	'var(--chart-series-8)'
];

/** One hue for magnitude, near-surface to strong, stepped separately per theme (layout.css). */
export const HEAT_RAMP = [
	'var(--chart-heat-1)',
	'var(--chart-heat-2)',
	'var(--chart-heat-3)',
	'var(--chart-heat-4)',
	'var(--chart-heat-5)',
	'var(--chart-heat-6)',
	'var(--chart-heat-7)'
];

/**
 * The backend pins booking outcomes to fixed hex colours (`charts.py`,
 * `_OUTCOME_COLORS`). An outcome is a state, not an identity, so each maps to
 * the reserved status token (themed) rather than being drawn as the raw hex.
 */
const BACKEND_COLORS = {
	'#16a34a': 'var(--chart-status-good)',
	'#9ca3af': 'var(--chart-muted)',
	'#dc2626': 'var(--chart-status-critical)',
	'#2563eb': 'var(--chart-series-1)'
};

/**
 * What each chart's values are, keyed by `chart_id` (backend `ChartId`).
 * `money` values arrive in major units (`charts.py::_major`); `percent` in
 * 0–100. A combo's second entry is its line's unit.
 * @type {Record<string, Unit | [Unit, Unit]>}
 */
const CHART_UNITS = {
	bookings_trend: 'count',
	revenue_trend: ['money', 'money'],
	booking_outcomes: 'count',
	revenue_by_service: 'money',
	revenue_by_provider: 'money',
	revenue_by_location: 'money',
	source_mix: 'count',
	new_vs_returning: 'count',
	retention_cohorts: 'percent',
	peak_hours: 'count',
	provider_utilization: 'percent',
	bookings_forecast: 'count',
	queue_wait_times: ['count', 'minutes'],
	payouts_breakdown: 'money',
	nova_charges: 'money',
	commission_by_class: 'money'
};

/**
 * @typedef {'count'|'money'|'percent'|'minutes'} Unit
 *
 * @typedef {Object} PlotlyTrace
 * @property {string} [type]
 * @property {string} [name]
 * @property {'h'|'v'} [orientation]
 * @property {string} [fill]
 * @property {(string|number)[]} [x]
 * @property {(number|string|null)[]} [y]
 * @property {string[]} [labels]
 * @property {number[]} [values]
 * @property {(number|null)[][]} [z]
 * @property {{ color?: string, colors?: string[] }} [marker]
 * @property {{ color?: string, dash?: string }} [line]
 *
 * @typedef {Object} PlotlyFigure
 * @property {PlotlyTrace[]} data
 * @property {Record<string, unknown>} [layout]
 *
 * @typedef {Object} Series
 * @property {string} key
 * @property {string} label
 * @property {string} color
 * @property {(number|null)[]} values One per category, null where there is no value.
 *
 * @typedef {{ type: 'columns', categories: string[], series: Series[], stacked: boolean, unit: Unit }} ColumnsModel
 * @typedef {{ type: 'ranked', rows: { label: string, value: number }[], unit: Unit }} RankedModel
 * @typedef {{ type: 'parts', parts: { label: string, value: number, color: string }[], unit: Unit }} PartsModel
 * @typedef {{ type: 'combo', columns: ColumnsModel, line: LineModel }} ComboModel
 * @typedef {{ type: 'line', categories: string[], series: Series[], band: { lower: number, upper: number }[]|null, forecastFrom: number|null, unit: Unit }} LineModel
 * @typedef {{ type: 'heatmap', columns: string[], rows: string[], values: (number|null)[][], max: number, unit: Unit, rowTitle: string, columnTitle: string }} HeatmapModel
 * @typedef {ColumnsModel|RankedModel|PartsModel|ComboModel|LineModel|HeatmapModel} ChartModel
 */

/** @param {unknown} value */
function toNumber(value) {
	if (value === null || value === undefined || value === '') return null;
	const number = Number(value);
	return Number.isFinite(number) ? number : null;
}

/** @param {PlotlyTrace} trace @param {number} index @param {number} count */
function seriesColor(trace, index, count) {
	const explicit = trace.marker?.color ?? trace.line?.color;
	if (typeof explicit === 'string' && explicit.toLowerCase() in BACKEND_COLORS) {
		return BACKEND_COLORS[/** @type {keyof typeof BACKEND_COLORS} */ (explicit.toLowerCase())];
	}
	// One series compares magnitude, not identity: it takes the first slot.
	return count > 1 ? CATEGORICAL_COLORS[index % CATEGORICAL_COLORS.length] : CATEGORICAL_COLORS[0];
}

/** @param {string} chartId @param {0|1} [which] @returns {Unit} */
function unitOf(chartId, which = 0) {
	const unit = CHART_UNITS[chartId] ?? 'count';
	return Array.isArray(unit) ? unit[which] : unit;
}

/**
 * @param {PlotlyTrace[]} traces bar or scatter traces sharing an x axis
 * @param {Unit} unit
 * @returns {{ categories: string[], series: Series[] }}
 */
function alignedSeries(traces, unit) {
	/** @type {string[]} */ const categories = [];
	const seen = new Map();
	for (const trace of traces) {
		for (const x of trace.x ?? []) {
			const key = String(x);
			if (!seen.has(key)) {
				seen.set(key, categories.length);
				categories.push(key);
			}
		}
	}
	const series = traces.map((trace, index) => {
		/** @type {(number|null)[]} */
		const values = categories.map(() => null);
		(trace.x ?? []).forEach((x, i) => {
			values[seen.get(String(x))] = toNumber(trace.y?.[i]);
		});
		return {
			key: `${index}`,
			label: trace.name || (unit === 'money' ? 'Revenue' : 'Value'),
			color: seriesColor(trace, index, traces.length),
			values
		};
	});
	return { categories, series };
}

/** @param {string} chartId @param {PlotlyFigure} figure @returns {ChartModel} */
function fromBars(chartId, figure) {
	const traces = (figure.data ?? []).filter((trace) => trace.type === 'bar');
	const unit = unitOf(chartId);
	if (traces.some((trace) => trace.orientation === 'h')) {
		const trace = traces[0];
		const rows = (trace.y ?? [])
			.map((label, i) => ({ label: String(label), value: toNumber(trace.x?.[i]) ?? 0 }))
			.sort((a, b) => b.value - a.value);
		return { type: 'ranked', rows, unit };
	}
	const { categories, series } = alignedSeries(traces, unit);
	return { type: 'columns', categories, series, stacked: series.length > 1, unit };
}

/**
 * Donuts become a part-to-whole bar: lengths along one line compare more
 * accurately than angles, and the parts stay readable when one dominates.
 * @param {string} chartId @param {PlotlyFigure} figure @returns {PartsModel}
 */
function fromPie(chartId, figure) {
	const trace = (figure.data ?? []).find((candidate) => candidate.type === 'pie');
	const labels = trace?.labels ?? [];
	const colors = trace?.marker?.colors;
	return {
		type: 'parts',
		unit: unitOf(chartId),
		parts: labels.map((label, i) => {
			const explicit = colors?.[i]?.toLowerCase();
			return {
				label: String(label),
				value: toNumber(trace?.values?.[i]) ?? 0,
				color:
					explicit && explicit in BACKEND_COLORS
						? BACKEND_COLORS[/** @type {keyof typeof BACKEND_COLORS} */ (explicit)]
						: CATEGORICAL_COLORS[i % CATEGORICAL_COLORS.length]
			};
		})
	};
}

/**
 * A bar and a line of different measures. Never one plot with two y-axes:
 * the panel draws two charts on one shared x axis.
 * @param {string} chartId @param {PlotlyFigure} figure @returns {ComboModel}
 */
function fromCombo(chartId, figure) {
	const traces = figure.data ?? [];
	const bar = traces.filter((trace) => trace.type === 'bar');
	const line = traces.filter((trace) => trace.type === 'scatter');
	const columns = alignedSeries(bar, unitOf(chartId, 0));
	const lineSeries = alignedSeries(line, unitOf(chartId, 1));
	// The line is a second measure, not a second identity: it takes the next slot.
	lineSeries.series.forEach((series) => (series.color = CATEGORICAL_COLORS[1]));
	return {
		type: 'combo',
		columns: { type: 'columns', ...columns, stacked: false, unit: unitOf(chartId, 0) },
		line: {
			type: 'line',
			...lineSeries,
			band: null,
			forecastFrom: null,
			unit: unitOf(chartId, 1)
		}
	};
}

/**
 * History, then a dashed trend with its band. Plotly draws the band as one
 * closed polygon (`fill: 'toself'`): upper edge forward, lower edge back.
 * @param {string} chartId @param {PlotlyFigure} figure @returns {LineModel}
 */
function fromForecast(chartId, figure) {
	const traces = figure.data ?? [];
	const bandTrace = traces.find((trace) => trace.fill === 'toself');
	const trendTrace = traces.find((trace) => trace.line?.dash === 'dash');
	const historyTrace = traces.find((trace) => trace !== bandTrace && trace !== trendTrace);

	const history = (historyTrace?.x ?? []).map(String);
	const trendX = (trendTrace?.x ?? []).map(String);
	// The trend starts on the last history week, so the two lines meet.
	const categories = [...history, ...trendX.filter((x) => !history.includes(x))];
	const forecastFrom = trendX.length ? history.length - 1 : null;

	/** @type {(number|null)[]} */
	const values = categories.map((category, i) => {
		if (i < history.length) return toNumber(historyTrace?.y?.[i]);
		return toNumber(trendTrace?.y?.[trendX.indexOf(category)]);
	});

	/** @type {{ lower: number, upper: number }[]|null} */
	let band = null;
	const bandX = bandTrace?.x ?? [];
	if (bandX.length && forecastFrom !== null) {
		const half = Math.floor(bandX.length / 2);
		const upper = (bandTrace?.y ?? []).slice(0, half);
		const lower = (bandTrace?.y ?? []).slice(half).reverse();
		const last = values[forecastFrom] ?? 0;
		band = categories.map((category, i) => {
			const at = bandX.slice(0, half).map(String).indexOf(category);
			if (at === -1) return { lower: i === forecastFrom ? last : NaN, upper: i === forecastFrom ? last : NaN };
			return { lower: toNumber(lower[at]) ?? 0, upper: toNumber(upper[at]) ?? 0 };
		});
	}

	return {
		type: 'line',
		categories,
		series: [
			{ key: '0', label: historyTrace?.name || 'Bookings', color: CATEGORICAL_COLORS[0], values }
		],
		band,
		forecastFrom,
		unit: unitOf(chartId)
	};
}

/** @param {string} chartId @param {PlotlyFigure} figure @returns {HeatmapModel} */
function fromHeatmap(chartId, figure) {
	const trace = (figure.data ?? []).find((candidate) => candidate.type === 'heatmap');
	const columns = (trace?.x ?? []).map(String);
	const rows = (trace?.y ?? []).map(String);
	let max = 0;
	const values = rows.map((_, r) =>
		columns.map((_, c) => {
			const value = toNumber(trace?.z?.[r]?.[c]);
			if (value !== null && value > max) max = value;
			return value;
		})
	);
	const cohorts = chartId === 'retention_cohorts';
	return {
		type: 'heatmap',
		columns,
		rows,
		values,
		max,
		unit: unitOf(chartId),
		rowTitle: cohorts ? 'First visit' : 'Day',
		columnTitle: cohorts ? 'Months since' : 'Hour'
	};
}

/**
 * The model for one chart, from its backend `kind` (`ChartKind`: bar,
 * stacked_bar, combo, donut, heatmap, forecast).
 * @param {{ chart_id: string, kind: string, figure: PlotlyFigure }} chart
 * @returns {ChartModel|null}
 */
export function chartModel(chart) {
	switch (chart.kind) {
		case 'bar':
		case 'stacked_bar':
			return fromBars(chart.chart_id, chart.figure);
		case 'donut':
			return fromPie(chart.chart_id, chart.figure);
		case 'combo':
			return fromCombo(chart.chart_id, chart.figure);
		case 'forecast':
			return fromForecast(chart.chart_id, chart.figure);
		case 'heatmap':
			return fromHeatmap(chart.chart_id, chart.figure);
		default:
			return null;
	}
}

/**
 * Whether there is anything to draw: a window with no bookings comes back as
 * a full axis of zeros, which would otherwise render as an empty frame.
 * @param {ChartModel} model
 */
export function hasData(model) {
	/** @param {(number|null)[]} values */
	const any = (values) => values.some((value) => value !== null && value !== 0);
	switch (model.type) {
		case 'columns':
		case 'line':
			return model.series.some((series) => any(series.values));
		case 'combo':
			return hasData(model.columns) || hasData(model.line);
		case 'ranked':
			return any(model.rows.map((row) => row.value));
		case 'parts':
			return any(model.parts.map((part) => part.value));
		case 'heatmap':
			return model.values.some(any);
	}
}

/**
 * The same numbers as a table, for the chart's table view.
 * @param {ChartModel} model
 * @param {(value: number|null, unit: Unit) => string} format
 * @param {(category: string) => string} formatCategory
 * @returns {{ head: string[], rows: string[][] }}
 */
export function tableOf(model, format, formatCategory) {
	switch (model.type) {
		case 'columns':
		case 'line':
			return {
				head: ['', ...model.series.map((series) => series.label)],
				rows: model.categories.map((category, i) => [
					formatCategory(category) + (model.type === 'line' && model.forecastFrom !== null && i > model.forecastFrom ? ' (trend)' : ''),
					...model.series.map((series) => format(series.values[i], model.unit))
				])
			};
		case 'combo':
			return {
				head: [
					'',
					...model.columns.series.map((series) => series.label),
					...model.line.series.map((series) => series.label)
				],
				rows: model.columns.categories.map((category, i) => [
					formatCategory(category),
					...model.columns.series.map((series) => format(series.values[i], model.columns.unit)),
					...model.line.series.map((series) => format(series.values[i] ?? null, model.line.unit))
				])
			};
		case 'ranked':
			return {
				head: ['', 'Value'],
				rows: model.rows.map((row) => [row.label, format(row.value, model.unit)])
			};
		case 'parts': {
			const total = model.parts.reduce((sum, part) => sum + part.value, 0);
			return {
				head: ['', 'Value', 'Share'],
				rows: model.parts.map((part) => [
					part.label,
					format(part.value, model.unit),
					total ? `${Math.round((part.value / total) * 100)}%` : '—'
				])
			};
		}
		case 'heatmap':
			return {
				head: [model.rowTitle, ...model.columns],
				rows: model.rows.map((row, r) => [
					formatCategory(row),
					...model.values[r].map((value) => format(value, model.unit))
				])
			};
	}
}
