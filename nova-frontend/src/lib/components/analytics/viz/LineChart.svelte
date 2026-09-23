<script>
	/**
	 * A 2px line over an ordered category axis, with a crosshair: the pointer
	 * anywhere over the plot snaps to the nearest category and reads out every
	 * series there. Gaps (null values) break the line rather than bridging it.
	 * For a forecast, points past `forecastFrom` are dashed and the band
	 * around them is a light wash of the line's own hue.
	 *
	 * The x positions are band centres, so a line drawn under a ColumnChart
	 * of the same categories lines up with its columns.
	 */
	import { scaleBand, scaleLinear } from 'd3-scale';
	import Tooltip from './Tooltip.svelte';
	import { formatCategory, formatTick, formatValue, labelStep } from './format.js';

	/**
	 * @type {{
	 *   model: import('../../../utils/chartData.js').LineModel,
	 *   height?: number,
	 *   currency?: string,
	 *   label?: string
	 * }}
	 */
	let { model, height = 240, currency = 'SAR', label = '' } = $props();

	const M = { top: 10, right: 4, bottom: 24, left: 44 };
	let width = $state(0);
	let hover = $state(/** @type {number|null} */ (null));

	let innerW = $derived(Math.max(0, width - M.left - M.right));
	let innerH = $derived(Math.max(0, height - M.top - M.bottom));

	let x = $derived(
		scaleBand()
			.domain(model.categories.map((_, i) => String(i)))
			.range([0, innerW])
			.paddingInner(0.3)
			.paddingOuter(0.15)
	);
	/** @param {number} i */
	const cx = (i) => (x(String(i)) ?? 0) + x.bandwidth() / 2;

	let peak = $derived(
		Math.max(
			1,
			...model.series.flatMap((series) => series.values.map((v) => v ?? 0)),
			...(model.band ?? []).map((b) => (Number.isFinite(b.upper) ? b.upper : 0))
		)
	);
	let y = $derived(scaleLinear().domain([0, peak]).range([innerH, 0]).nice(4));
	let ticks = $derived(y.ticks(4));
	let step = $derived(labelStep(model.categories.length, innerW));

	/**
	 * The line as path runs: a null ends a run, and the forecast part is a
	 * run of its own so it can be dashed.
	 * @param {(number|null)[]} values
	 */
	function runs(values) {
		/** @type {{ d: string, dashed: boolean }[]} */
		const out = [];
		let d = '';
		let dashed = false;
		values.forEach((value, i) => {
			const isForecast = model.forecastFrom !== null && i > model.forecastFrom;
			if (value === null) {
				if (d) out.push({ d, dashed });
				d = '';
				return;
			}
			if (d && isForecast !== dashed) {
				out.push({ d, dashed });
				// Start the dashed run on the last solid point so the two meet.
				d = `M${cx(i - 1)},${y(values[i - 1] ?? 0)}`;
			}
			dashed = isForecast;
			d += `${d ? 'L' : 'M'}${cx(i)},${y(value)}`;
		});
		if (d) out.push({ d, dashed });
		return out;
	}

	/** Points with no neighbour to join, which a line alone would not show. */
	/** @param {(number|null)[]} values */
	function isolated(values) {
		return values
			.map((value, i) => ({ value, i }))
			.filter(
				({ value, i }) =>
					value !== null && (values[i - 1] ?? null) === null && (values[i + 1] ?? null) === null
			);
	}

	let bandPath = $derived.by(() => {
		const band = model.band;
		if (!band) return '';
		const idx = band.map((b, i) => ({ ...b, i })).filter((b) => Number.isFinite(b.upper));
		if (idx.length < 2) return '';
		const top = idx.map((b) => `${cx(b.i)},${y(b.upper)}`).join('L');
		const bottom = idx
			.slice()
			.reverse()
			.map((b) => `${cx(b.i)},${y(b.lower)}`)
			.join('L');
		return `M${top}L${bottom}Z`;
	});

	/** @param {PointerEvent} event */
	function onmove(event) {
		const box = /** @type {SVGElement} */ (event.currentTarget).getBoundingClientRect();
		const px = event.clientX - box.left - M.left;
		const i = Math.round((px - x.bandwidth() / 2 - (x(String(0)) ?? 0)) / x.step());
		hover = Math.max(0, Math.min(model.categories.length - 1, i));
	}

	/** @param {number|null|undefined} value */
	const fmt = (value) => formatValue(value, model.unit, { currency });

	let tip = $derived.by(() => {
		if (hover === null) return null;
		const i = hover;
		const top = Math.max(...model.series.map((series) => series.values[i] ?? 0));
		const isForecast = model.forecastFrom !== null && i > model.forecastFrom;
		const rows = model.series.map((series) => ({
			label: isForecast ? `${series.label} (trend)` : series.label,
			value: fmt(series.values[i]),
			color: series.color
		}));
		const b = model.band?.[i];
		if (isForecast && b && Number.isFinite(b.upper)) {
			rows.push({ label: 'Likely range', value: `${fmt(b.lower)} – ${fmt(b.upper)}`, color: '' });
		}
		return {
			x: M.left + cx(i),
			y: M.top + Math.min(y(top), innerH - 48) - 8,
			title: formatCategory(model.categories[i], { long: true }),
			rows
		};
	});
</script>

<div class="relative w-full" bind:clientWidth={width} style:height={`${height}px`}>
	{#if width > 0}
		<svg
			{width}
			{height}
			role="img"
			aria-label={label}
			class="block overflow-visible"
			onpointermove={onmove}
			onpointerleave={() => (hover = null)}
		>
			<g transform={`translate(${M.left},${M.top})`}>
				{#each ticks as tick (tick)}
					<line
						x1="0"
						x2={innerW}
						y1={y(tick)}
						y2={y(tick)}
						class={tick === 0 ? 'stroke-line-strong' : 'stroke-line-subtle'}
						stroke-width="1"
						shape-rendering="crispEdges"
					/>
					<text
						x="-8"
						y={y(tick)}
						dy="0.32em"
						text-anchor="end"
						class="fill-fg-subtle text-[11px] tabular-nums">{formatTick(tick, model.unit)}</text
					>
				{/each}

				{#if model.forecastFrom !== null}
					<rect
						x={cx(model.forecastFrom)}
						y="0"
						width={Math.max(0, innerW - cx(model.forecastFrom))}
						height={innerH}
						class="fill-surface-sunken"
					/>
					<text
						x={cx(model.forecastFrom) + 6}
						y="10"
						class="fill-fg-subtle text-[11px] font-medium">Trend</text
					>
				{/if}

				{#if bandPath}
					<path
						d={bandPath}
						fill={model.series[0]?.color}
						opacity="0.14"
						stroke="none"
					/>
				{/if}

				{#if hover !== null}
					<line
						x1={cx(hover)}
						x2={cx(hover)}
						y1="0"
						y2={innerH}
						class="stroke-line-strong"
						stroke-width="1"
						shape-rendering="crispEdges"
					/>
				{/if}

				{#each model.series as series (series.key)}
					{#each runs(series.values) as run, r (r)}
						<path
							d={run.d}
							fill="none"
							stroke={series.color}
							stroke-width="2"
							stroke-linejoin="round"
							stroke-linecap="round"
							stroke-dasharray={run.dashed ? '5 4' : undefined}
						/>
					{/each}
					{#each isolated(series.values) as point (point.i)}
						<circle cx={cx(point.i)} cy={y(point.value ?? 0)} r="3" fill={series.color} />
					{/each}
					{#if hover !== null && series.values[hover] !== null}
						<circle
							cx={cx(hover)}
							cy={y(series.values[hover] ?? 0)}
							r="4.5"
							fill={series.color}
							class="stroke-surface"
							stroke-width="2"
						/>
					{/if}
				{/each}

				{#each model.categories as category, i (i)}
					{#if i % step === 0}
						<text x={cx(i)} y={innerH + 16} text-anchor="middle" class="fill-fg-subtle text-[11px]"
							>{formatCategory(category)}</text
						>
					{/if}
				{/each}
				<rect x="0" y="0" width={innerW} height={innerH} fill="transparent" />
			</g>
		</svg>
		{#if tip}
			<Tooltip {width} {...tip} />
		{/if}
	{/if}
</div>
