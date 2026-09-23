<script>
	/**
	 * Vertical columns over an ordered category axis (usually days), one
	 * series or several stacked. Marks follow the chart kit's spec: at most
	 * 24px wide, the data end rounded 4px and the base flush on the axis, a
	 * 2px surface gap between stacked segments, a hairline grid behind.
	 * Hovering anywhere in a column's band shows its values; the band is the
	 * hit target, so thin columns are still easy to point at.
	 */
	import { scaleBand, scaleLinear } from 'd3-scale';
	import Tooltip from './Tooltip.svelte';
	import { barPath, formatCategory, formatTick, formatValue, labelStep } from './format.js';

	/**
	 * @type {{
	 *   model: import('../../../utils/chartData.js').ColumnsModel,
	 *   height?: number,
	 *   currency?: string,
	 *   showXAxis?: boolean,
	 *   label?: string
	 * }}
	 */
	let { model, height = 240, currency = 'SAR', showXAxis = true, label = '' } = $props();

	const M = { top: 8, right: 4, bottom: 24, left: 44 };
	let width = $state(0);
	let hover = $state(/** @type {number|null} */ (null));

	let bottom = $derived(showXAxis ? M.bottom : 6);
	let innerW = $derived(Math.max(0, width - M.left - M.right));
	let innerH = $derived(Math.max(0, height - M.top - bottom));

	let totals = $derived(
		model.categories.map((_, i) =>
			model.series.reduce((sum, series) => sum + Math.max(0, series.values[i] ?? 0), 0)
		)
	);
	let x = $derived(
		scaleBand()
			.domain(model.categories.map((_, i) => String(i)))
			.range([0, innerW])
			.paddingInner(0.3)
			.paddingOuter(0.15)
	);
	let y = $derived(
		scaleLinear()
			.domain([0, Math.max(1, ...totals)])
			.range([innerH, 0])
			.nice(4)
	);
	let ticks = $derived(y.ticks(4));
	let barW = $derived(Math.max(2, Math.min(24, x.bandwidth())));
	let step = $derived(labelStep(model.categories.length, innerW));

	/** Each column's segments bottom-up, with the gap and the rounded top applied. */
	let columns = $derived(
		model.categories.map((_, i) => {
			const cx = (x(String(i)) ?? 0) + x.bandwidth() / 2;
			let base = 0;
			const filled = model.series
				.map((series) => ({ series, value: Math.max(0, series.values[i] ?? 0) }))
				.filter((segment) => segment.value > 0);
			return filled.map((segment, s) => {
				const y0 = y(base);
				const y1 = y(base + segment.value);
				base += segment.value;
				const isTop = s === filled.length - 1;
				// The gap comes out of the segment below, so the stack's total height is true.
				const h = Math.max(1, y0 - y1 - (isTop ? 0 : 2));
				return {
					key: segment.series.key,
					color: segment.series.color,
					d: barPath(cx - barW / 2, isTop ? y1 : y1 + 2, barW, h, 4, isTop ? 'top' : 'none')
				};
			});
		})
	);

	/** @param {number|null|undefined} value */
	const fmt = (value) => formatValue(value, model.unit, { currency });

	let tip = $derived.by(() => {
		if (hover === null) return null;
		const i = hover;
		const rows = model.series
			.map((series) => ({ label: series.label, value: fmt(series.values[i]), color: series.color }))
			.reverse();
		if (model.stacked) rows.push({ label: 'Total', value: fmt(totals[i]), color: '', strong: true });
		return {
			x: M.left + (x(String(i)) ?? 0) + x.bandwidth() / 2,
			y: M.top + Math.min(y(totals[i]), innerH - 40) - 8,
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

				{#if hover !== null}
					<rect
						x={(x(String(hover)) ?? 0) - (x.step() * x.paddingInner()) / 2}
						y="0"
						width={x.step()}
						height={innerH}
						class="fill-surface-muted"
						opacity="0.7"
					/>
				{/if}

				{#each columns as segments, i (i)}
					<g
						opacity={hover === null || hover === i ? 1 : 0.55}
						class="transition-opacity duration-fast"
					>
						{#each segments as segment (segment.key)}
							<path d={segment.d} fill={segment.color} />
						{/each}
					</g>
				{/each}

				{#if showXAxis}
					{#each model.categories as category, i (i)}
						{#if i % step === 0}
							<text
								x={(x(String(i)) ?? 0) + x.bandwidth() / 2}
								y={innerH + 16}
								text-anchor="middle"
								class="fill-fg-subtle text-[11px]">{formatCategory(category)}</text
							>
						{/if}
					{/each}
				{/if}

				{#each model.categories as _, i (i)}
					<rect
						role="presentation"
						x={(x(String(i)) ?? 0) - (x.step() * x.paddingInner()) / 2}
						y="0"
						width={x.step()}
						height={innerH}
						fill="transparent"
						onpointerenter={() => (hover = i)}
					/>
				{/each}
			</g>
		</svg>
		{#if tip}
			<Tooltip {width} {...tip} />
		{/if}
	{/if}
</div>
