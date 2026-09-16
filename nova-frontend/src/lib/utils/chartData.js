/**
 * Turns the Plotly figure JSON that `analytics.getChart` returns
 * (nova_backend/app/modules/analytics/charts.py — `data` traces plus `layout`)
 * into plain arrays layerchart's components can draw directly, so the
 * frontend never depends on plotly.js. Detection reads trace *structure*
 * (`type`, `orientation`, `fill`, `line.dash`) rather than trace names, since
 * names are localised (English or Arabic) and structure isn't.
 *
 * The categorical order and the sequential ramp both come from the design
 * system's validated palette (see layout.css) — never reassign the order or
 * generate a new hue here.
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

/** One hue, light to dark, for magnitude (heatmap cells). */
export const SEQUENTIAL_BLUE = [
	'var(--chart-sequential-100)',
	'var(--chart-sequential-200)',
	'var(--chart-sequential-300)',
	'var(--chart-sequential-400)',
	'var(--chart-sequential-500)',
	'var(--chart-sequential-600)',
	'var(--chart-sequential-700)'
];

/** Booking outcomes are a state, not an identity — status colors, matching the backend's own semantics. */
export const OUTCOME_COLORS = {
	completed: 'var(--chart-status-good)',
	cancelled: 'var(--chart-muted)',
	no_show: 'var(--chart-status-critical)',
	upcoming: 'var(--chart-series-1)'
};

/**
 * @typedef {Object} PlotlyTrace
 * @property {string} [type]
 * @property {string} [name]
 * @property {'h'|'v'} [orientation]
 * @property {string} [fill]
 * @property {(string|number)[]} [x]
 * @property {number[]} [y]
 * @property {string[]} [labels]
 * @property {number[]} [values]
 * @property {number[][]} [z]
 * @property {number} [hole]
 * @property {{ color?: string, colors?: string[] }} [marker]
 * @property {{ color?: string, dash?: string }} [line]
 */
/**
 * @typedef {Object} PlotlyFigure
 * @property {PlotlyTrace[]} data
 * @property {Record<string, unknown>} [layout]
 */

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}/;

/**
 * A Plotly-serialised category value, as a Date when it looks like one, else as-is.
 * @param {string|number} value
 */
function parseCategory(value) {
	if (typeof value === 'string' && ISO_DATE_RE.test(value)) {
		const date = new Date(value);
		if (!Number.isNaN(date.getTime())) return date;
	}
	return value;
}

/** @param {PlotlyTrace} trace @param {number} index */
function resolveColor(trace, index) {
	const explicit = trace.marker?.color ?? trace.line?.color;
	if (typeof explicit === 'string') return explicit;
	return CATEGORICAL_COLORS[index % CATEGORICAL_COLORS.length];
}

/**
 * @typedef {Object} BarPoint
 * @property {unknown} category
 * @property {number|null} value
 */

/**
 * @typedef {Object} BarSeries
 * @property {string} key
 * @property {string|undefined} label
 * @property {string} color
 * @property {BarPoint[]} data
 */

/**
 * BAR and STACKED_BAR kinds: one or more `bar` traces sharing a category axis.
 * @param {PlotlyFigure} figure
 * @returns {{ orientation: 'horizontal'|'vertical', series: BarSeries[] }}
 */
export function barSeriesFromFigure(figure) {
	const traces = (figure.data ?? []).filter((trace) => trace.type === 'bar');
	const orientation = traces.some((trace) => trace.orientation === 'h') ? 'horizontal' : 'vertical';

	const series = traces.map((trace, index) => {
		const categories = orientation === 'horizontal' ? trace.y : trace.x;
		// Plotly's `x`/`y` swap meaning with orientation, so whichever one is the
		// value axis here is numeric even though its declared type spans both.
		const values = /** @type {number[]|undefined} */ (
			orientation === 'horizontal' ? trace.x : trace.y
		);
		return {
			key: trace.name || `series_${index}`,
			label: trace.name || undefined,
			// A single-series bar compares magnitude across categories, not identity —
			// the sequential default, not a categorical hue (choosing-a-form.md).
			color:
				traces.length > 1
					? resolveColor(trace, index)
					: (trace.marker?.color ?? 'var(--chart-sequential-500)'),
			data: (categories ?? []).map((category, i) => ({
				category: parseCategory(category),
				value: values?.[i] ?? null
			}))
		};
	});

	return { orientation, series };
}

/**
 * @typedef {Object} DonutSlice
 * @property {string} key
 * @property {string} label
 * @property {number} value
 * @property {string} color
 */

/**
 * DONUT kind: a single `pie` trace.
 * @param {PlotlyFigure} figure
 * @returns {{ slices: DonutSlice[], hole: number }}
 */
export function donutDataFromFigure(figure) {
	const trace = (figure.data ?? []).find((candidate) => candidate.type === 'pie');
	if (!trace) return { slices: [], hole: 0.55 };

	const labels = trace.labels ?? [];
	const values = trace.values ?? [];
	const explicitColors = trace.marker?.colors;

	const slices = labels.map((label, index) => ({
		key: String(label),
		label: String(label),
		value: values[index] ?? 0,
		color: explicitColors?.[index] ?? CATEGORICAL_COLORS[index % CATEGORICAL_COLORS.length]
	}));

	return { slices, hole: typeof trace.hole === 'number' ? trace.hole : 0.55 };
}

/**
 * @typedef {Object} ComboSeries
 * @property {string} label
 * @property {BarPoint[]} data
 */

/**
 * COMBO kind: one `bar` trace plus one `scatter` trace sharing an x axis.
 * Rendered as two single-axis panels rather than a dual-axis chart — a
 * second y-scale on one plot reads two different stories as one (see the
 * dataviz skill's anti-patterns: "One axis").
 * @param {PlotlyFigure} figure
 * @returns {{ bar: ComboSeries|null, line: ComboSeries|null }}
 */
export function comboSeriesFromFigure(figure) {
	const traces = figure.data ?? [];
	const barTrace = traces.find((trace) => trace.type === 'bar');
	const lineTrace = traces.find((trace) => trace.type === 'scatter');

	/** @param {PlotlyTrace|undefined} trace @returns {ComboSeries|null} */
	function toSeries(trace) {
		if (!trace) return null;
		const xValues = trace.x ?? [];
		const yValues = trace.y ?? [];
		return {
			label: trace.name ?? '',
			data: xValues.map((x, i) => ({ category: parseCategory(x), value: yValues[i] ?? null }))
		};
	}

	return { bar: toSeries(barTrace), line: toSeries(lineTrace) };
}

/**
 * @typedef {Object} ForecastPoint
 * @property {unknown} date
 * @property {number|null} value
 */
/**
 * @typedef {Object} ForecastBandPoint
 * @property {unknown} date
 * @property {number} lower
 * @property {number} upper
 */

/**
 * FORECAST kind: a solid history line, an optional filled confidence band
 * (`fill: 'toself'`, a mirrored polygon Plotly draws it as), and an optional
 * dashed trend line continuing from the last history point.
 * @param {PlotlyFigure} figure
 * @returns {{ history: ForecastPoint[], band: ForecastBandPoint[], trend: ForecastPoint[] }}
 */
export function forecastFromFigure(figure) {
	const traces = figure.data ?? [];
	const bandTrace = traces.find((trace) => trace.fill === 'toself');
	const trendTrace = traces.find((trace) => trace.line?.dash === 'dash');
	const historyTrace = traces.find((trace) => trace !== bandTrace && trace !== trendTrace);

	const historyX = historyTrace?.x ?? [];
	const historyY = historyTrace?.y ?? [];
	const history = historyX.map((x, i) => ({ date: parseCategory(x), value: historyY[i] ?? null }));

	/** @type {ForecastBandPoint[]} */
	let band = [];
	const bandX = bandTrace?.x ?? [];
	const bandY = bandTrace?.y ?? [];
	if (bandX.length > 0) {
		const half = Math.floor(bandX.length / 2);
		const weeks = bandX.slice(0, half);
		const upper = bandY.slice(0, half);
		const lower = bandY.slice(half).slice().reverse();
		band = weeks.map((x, i) => ({ date: parseCategory(x), lower: lower[i], upper: upper[i] }));
	}

	const trendX = trendTrace?.x ?? [];
	const trendY = trendTrace?.y ?? [];
	const trend = trendX.map((x, i) => ({ date: parseCategory(x), value: trendY[i] ?? null }));

	return { history, band, trend };
}

/**
 * @typedef {Object} HeatmapCell
 * @property {string} column
 * @property {string} row
 * @property {number} value
 */

/**
 * HEATMAP kind: a single `heatmap` trace (`x` columns, `y` rows, `z` matrix).
 * @param {PlotlyFigure} figure
 * @returns {{ columns: string[], rows: string[], cells: HeatmapCell[], min: number, max: number }}
 */
export function heatmapDataFromFigure(figure) {
	const trace = (figure.data ?? []).find((candidate) => candidate.type === 'heatmap');
	if (!trace) return { columns: [], rows: [], cells: [], min: 0, max: 0 };

	const columns = (trace.x ?? []).map(String);
	const rows = (trace.y ?? []).map(String);
	const matrix = trace.z ?? [];

	/** @type {HeatmapCell[]} */
	const cells = [];
	let min = Infinity;
	let max = -Infinity;
	rows.forEach((row, rowIndex) => {
		columns.forEach((column, columnIndex) => {
			const value = matrix[rowIndex]?.[columnIndex] ?? 0;
			cells.push({ column, row, value });
			if (value < min) min = value;
			if (value > max) max = value;
		});
	});
	if (!Number.isFinite(min)) min = 0;
	if (!Number.isFinite(max)) max = 0;

	return { columns, rows, cells, min, max };
}
