<script>
	/**
	 * The shape of a number over the window, beside the number itself: no
	 * axes, no labels, just a 2px line on a faint wash of its own hue. It is
	 * decoration for a figure already written out, so it is hidden from
	 * assistive tech.
	 *
	 * @type {{ values: (number|null)[], color?: string, height?: number }}
	 */
	let { values, color = 'var(--chart-series-1)', height = 40 } = $props();

	let width = $state(0);
	let path = $derived.by(() => {
		const points = values.map((v) => v ?? 0);
		if (points.length < 2 || width <= 0) return null;
		const max = Math.max(...points);
		if (max <= 0) return null;
		const step = width / (points.length - 1);
		const line = points
			.map(
				(v, i) =>
					`${i ? 'L' : 'M'}${(i * step).toFixed(1)},${(2 + (1 - v / max) * (height - 4)).toFixed(1)}`
			)
			.join('');
		return { line, area: `${line}L${width},${height}L0,${height}Z` };
	});
</script>

<div class="w-full" bind:clientWidth={width} style:height={`${height}px`} aria-hidden="true">
	{#if path}
		<svg {width} {height} class="block overflow-visible">
			<path d={path.area} fill={color} opacity="0.1" />
			<path d={path.line} fill="none" stroke={color} stroke-width="2" stroke-linejoin="round" />
		</svg>
	{/if}
</div>
