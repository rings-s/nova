<script>
	/**
	 * Fetches one chart (docs/13 section 7) and hands its Plotly figure JSON
	 * straight to plotly.js — the backend builds `figure` for exactly this.
	 * `plotly.js-dist-min` is loaded lazily so it never weighs on a page that
	 * doesn't render a chart.
	 */
	import { getChart } from '../../api/analytics.js';
	import Spinner from '../ui/Spinner.svelte';
	import Alert from '../ui/Alert.svelte';

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
		height = 320
	} = $props();

	/** @type {HTMLDivElement|undefined} */
	let container;
	let loading = $state(true);
	let error = $state(/** @type {string|null} */ (null));
	let chart = $state(/** @type {import('../../api/analytics.js').Chart|null} */ (null));
	/** @type {any} Cached module handle, so cleanup doesn't need a second import. */
	let plotly = null;

	$effect(() => {
		let cancelled = false;
		loading = true;
		error = null;
		getChart(tenantId, chartId, { businessId, dateFrom, dateTo, granularity, locale })
			.then((result) => {
				if (!cancelled) chart = result;
			})
			.catch((err) => {
				if (!cancelled) error = err?.message ?? 'Could not load this chart.';
			})
			.finally(() => {
				if (!cancelled) loading = false;
			});
		return () => {
			cancelled = true;
		};
	});

	$effect(() => {
		if (!chart || !container) return;
		let disposed = false;
		import('plotly.js-dist-min').then((module) => {
			if (disposed) return;
			plotly = module.default ?? module;
			plotly.newPlot(
				container,
				chart.figure.data ?? [],
				{ ...chart.figure.layout, autosize: true },
				{ responsive: true, displaylogo: false }
			);
		});
		return () => {
			disposed = true;
			if (plotly && container) plotly.purge(container);
		};
	});
</script>

<div class="relative">
	{#if loading}
		<div class="flex justify-center py-8"><Spinner /></div>
	{:else if error}
		<Alert tone="error">{error}</Alert>
	{/if}
	<div bind:this={container} style={`height: ${height}px`} class={loading || error ? 'hidden' : ''}></div>
</div>
