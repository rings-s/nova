<script>
	/**
	 * BAR and STACKED_BAR chart kinds (docs/13 section 7). Each backend series
	 * carries its own `data` array (layerchart's "per-series data" pattern),
	 * so no pivoting is needed — one Plotly trace maps to one series as-is.
	 */
	import { BarChart } from 'layerchart';

	/**
	 * @type {{
	 *   orientation: 'horizontal'|'vertical',
	 *   series: import('../../../utils/chartData.js').BarSeries[],
	 *   height?: number
	 * }}
	 */
	let { orientation, series, height = 280 } = $props();

	let categoryKey = $derived(orientation === 'horizontal' ? 'value' : 'category');
	let valueKey = $derived(orientation === 'horizontal' ? 'category' : 'value');
</script>

<BarChart
	{orientation}
	x={categoryKey}
	y={valueKey}
	series={series.map((s) => ({ key: s.key, label: s.label, color: s.color, data: s.data }))}
	seriesLayout={series.length > 1 ? 'stack' : undefined}
	legend={series.length > 1}
	{height}
/>
