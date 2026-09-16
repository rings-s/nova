<script>
	/**
	 * HEATMAP chart kind (peak hours, retention cohorts): a grid of cells
	 * colored by magnitude on the sequential blue ramp — never a rainbow scale.
	 */
	import { Chart, Svg, Layer, Axis, Cell } from 'layerchart';
	import { scaleBand, scaleQuantize } from 'd3-scale';
	import { SEQUENTIAL_BLUE } from '../../../utils/chartData.js';

	/**
	 * @type {{
	 *   columns: string[],
	 *   rows: string[],
	 *   cells: import('../../../utils/chartData.js').HeatmapCell[],
	 *   min: number,
	 *   max: number,
	 *   height?: number
	 * }}
	 */
	let { columns, rows, cells, min, max, height = 280 } = $props();
</script>

<Chart
	data={cells}
	x="column"
	xScale={scaleBand()}
	xDomain={columns}
	y="row"
	yScale={scaleBand()}
	yDomain={rows}
	c="value"
	cScale={scaleQuantize()}
	cDomain={[min, max]}
	cRange={SEQUENTIAL_BLUE}
	padding={{ top: 4, bottom: 28, left: 72, right: 4 }}
	{height}
>
	<Svg>
		<Layer>
			<Axis placement="bottom" rule />
			<Axis placement="left" rule />
			<Cell x="column" y="row" fill="value" insets={{ all: 1 }} />
		</Layer>
	</Svg>
</Chart>
