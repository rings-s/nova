<script>
	/** DONUT chart kind — a single categorical pie, part-to-whole. */
	import { PieChart } from 'layerchart';

	/**
	 * @type {{ slices: import('../../../utils/chartData.js').DonutSlice[], hole?: number, height?: number }}
	 */
	let { slices, hole = 0.55, height = 280 } = $props();
</script>

<PieChart
	data={slices}
	key="key"
	label="label"
	value="value"
	cDomain={slices.map((slice) => slice.key)}
	cRange={slices.map((slice) => slice.color)}
	innerRadius={hole}
	legend
	{height}
/>
