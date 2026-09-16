<script>
	/**
	 * FORECAST chart kind: a solid history line, a dashed trend continuing
	 * from it, and a shaded confidence band underneath — composed from
	 * primitives since it's three marks sharing one axis, not one of
	 * layerchart's streamlined chart wrappers.
	 */
	import { Chart, Svg, Layer, Axis, Area, Spline } from 'layerchart';

	/**
	 * @type {{
	 *   history: import('../../../utils/chartData.js').ForecastPoint[],
	 *   band: import('../../../utils/chartData.js').ForecastBandPoint[],
	 *   trend: import('../../../utils/chartData.js').ForecastPoint[],
	 *   height?: number
	 * }}
	 */
	let { history, band, trend, height = 280 } = $props();
</script>

<Chart
	data={history}
	x="date"
	y="value"
	yDomain={[0, null]}
	yNice
	padding={{ left: 44, bottom: 28, top: 8, right: 12 }}
	{height}
>
	<Svg>
		<Layer>
			<Axis placement="left" grid rule />
			<Axis placement="bottom" rule />
			{#if band.length > 0}
				<Area
					data={band}
					x="date"
					y0="lower"
					y1="upper"
					fill="var(--chart-series-1)"
					fillOpacity={0.15}
					line={false}
				/>
			{/if}
			<Spline data={history} x="date" y="value" stroke="var(--chart-series-1)" class="stroke-2" />
			{#if trend.length > 0}
				<Spline
					data={trend}
					x="date"
					y="value"
					stroke="var(--chart-series-1)"
					class="stroke-2 [stroke-dasharray:4_4]"
				/>
			{/if}
		</Layer>
	</Svg>
</Chart>
