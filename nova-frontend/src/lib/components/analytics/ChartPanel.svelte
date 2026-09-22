<script>
	/**
	 * Fetches one chart (docs/13 section 7) and renders it with layerchart,
	 * picking the mark set from `chart.kind` (nova_backend's `ChartKind`:
	 * bar, stacked_bar, combo, donut, heatmap, forecast). The backend's
	 * `figure` is Plotly JSON — `$lib/utils/chartData.js` reads it structurally
	 * so this never needs plotly.js on the client.
	 */
	import { getChart } from '../../api/analytics.js';
	import { ApiError } from '../../api/client.js';
	import {
		barSeriesFromFigure,
		donutDataFromFigure,
		comboSeriesFromFigure,
		forecastFromFigure,
		heatmapDataFromFigure
	} from '../../utils/chartData.js';
	import { errorMessage } from '../../utils/errors.js';
	import Skeleton from '../ui/Skeleton.svelte';
	import Alert from '../ui/Alert.svelte';
	import BarSeriesChart from './charts/BarSeriesChart.svelte';
	import DonutChart from './charts/DonutChart.svelte';
	import ComboChart from './charts/ComboChart.svelte';
	import ForecastChart from './charts/ForecastChart.svelte';
	import HeatmapChart from './charts/HeatmapChart.svelte';

	/**
	 * @type {{
	 *   tenantId: string,
	 *   chartId: string,
	 *   businessId: string,
	 *   dateFrom?: string|null,
	 *   dateTo?: string|null,
	 *   granularity?: import('../../api/analytics.js').Granularity|null,
	 *   locale?: 'en'|'ar',
	 *   height?: number
	 * }}
	 */
	let {
		tenantId,
		chartId,
		businessId,
		dateFrom = null,
		dateTo = null,
		granularity = null,
		locale = 'en',
		height = 280
	} = $props();

	let loading = $state(true);
	let error = $state(/** @type {string|null} */ (null));
	/** `insufficient_data` (a fresh business with no history yet, docs/13's
	 * forecast needs 8 complete weeks) is an expected state, not a failure —
	 * shown as a quiet note rather than an alarming red banner. */
	let errorIsExpected = $state(false);
	let chart = $state(/** @type {import('../../api/analytics.js').Chart|null} */ (null));

	$effect(() => {
		let cancelled = false;
		loading = true;
		error = null;
		errorIsExpected = false;
		getChart(tenantId, chartId, { businessId, dateFrom, dateTo, granularity, locale })
			.then((result) => {
				if (!cancelled) chart = result;
			})
			.catch((err) => {
				if (!cancelled) {
					error = errorMessage(err);
					errorIsExpected = err instanceof ApiError && err.code === 'insufficient_data';
				}
			})
			.finally(() => {
				if (!cancelled) loading = false;
			});
		return () => {
			cancelled = true;
		};
	});
</script>

<div class="min-w-0">
	<p class="text-sm font-semibold text-fg">{chart?.title ?? ''}</p>
	{#if chart?.description}
		<p class="mb-3 text-xs text-fg-muted">{chart.description}</p>
	{/if}

	{#if loading}
		<Skeleton class="h-[220px] w-full rounded-control" />
	{:else if error}
		<Alert tone={errorIsExpected ? 'info' : 'error'}>{error}</Alert>
	{:else if chart}
		{#if chart.kind === 'bar' || chart.kind === 'stacked_bar'}
			{@const { orientation, series } = barSeriesFromFigure(chart.figure)}
			<BarSeriesChart {orientation} {series} {height} />
		{:else if chart.kind === 'donut'}
			{@const { slices, hole } = donutDataFromFigure(chart.figure)}
			<DonutChart {slices} {hole} {height} />
		{:else if chart.kind === 'combo'}
			{@const { bar, line } = comboSeriesFromFigure(chart.figure)}
			<ComboChart {bar} {line} height={height / 2} />
		{:else if chart.kind === 'forecast'}
			{@const { history, band, trend } = forecastFromFigure(chart.figure)}
			<ForecastChart {history} {band} {trend} {height} />
		{:else if chart.kind === 'heatmap'}
			{@const { columns, rows, cells, min, max } = heatmapDataFromFigure(chart.figure)}
			<HeatmapChart {columns} {rows} {cells} {min} {max} {height} />
		{:else}
			<Alert tone="warning">Unsupported chart kind: {chart.kind}</Alert>
		{/if}
	{/if}
</div>
