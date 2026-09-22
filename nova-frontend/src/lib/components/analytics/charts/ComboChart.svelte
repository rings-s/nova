<script>
	/**
	 * COMBO chart kind. The backend pairs a bar series with a line series on a
	 * secondary Plotly axis (e.g. revenue + average ticket). Rendered here as
	 * two single-axis panels sharing the same category order, rather than one
	 * dual-axis plot — a second y-scale on one plot reads two different
	 * stories as one (dataviz skill, "One axis").
	 */
	import { BarChart, LineChart } from 'layerchart';

	/**
	 * @type {{
	 *   bar: import('../../../utils/chartData.js').ComboSeries|null,
	 *   line: import('../../../utils/chartData.js').ComboSeries|null,
	 *   height?: number
	 * }}
	 */
	let { bar, line, height = 160 } = $props();
</script>

<div class="flex flex-col gap-4">
	{#if bar}
		<div>
			<p class="mb-1 text-xs font-medium text-fg-muted">{bar.label}</p>
			<BarChart
				data={bar.data}
				x="category"
				y="value"
				series={[{ key: 'value', color: 'var(--chart-series-1)' }]}
				{height}
			/>
		</div>
	{/if}
	{#if line}
		<div>
			<p class="mb-1 text-xs font-medium text-fg-muted">{line.label}</p>
			<LineChart
				data={line.data}
				x="category"
				y="value"
				series={[{ key: 'value', color: 'var(--chart-series-2)' }]}
				{height}
			/>
		</div>
	{/if}
</div>
