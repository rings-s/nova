<script>
	/**
	 * The hover card for a chart mark. Positioned inside the chart's own
	 * relative box and flipped away from the edge it would overflow; it never
	 * takes the pointer, so it can't flicker the hover it belongs to.
	 *
	 * @type {{
	 *   x: number,
	 *   y: number,
	 *   width: number,
	 *   title?: string,
	 *   rows: { label: string, value: string, color?: string, strong?: boolean }[]
	 * }}
	 */
	let { x, y, width, title = '', rows } = $props();

	let flip = $derived(x > width / 2);
</script>

<div
	class="pointer-events-none absolute z-10 min-w-36 animate-fade-in rounded-control border border-line bg-surface/95 px-3 py-2 text-xs shadow-overlay backdrop-blur"
	style:left={flip ? 'auto' : `${x + 12}px`}
	style:right={flip ? `${width - x + 12}px` : 'auto'}
	style:top={`${Math.max(0, y)}px`}
	role="presentation"
>
	{#if title}
		<p class="mb-1.5 font-medium text-fg-muted">{title}</p>
	{/if}
	<ul class="flex flex-col gap-1">
		{#each rows as row, i (i)}
			<li class="flex items-center justify-between gap-4">
				<span class="flex min-w-0 items-center gap-2 text-fg-secondary">
					{#if row.color}
						<span class="size-2 shrink-0 rounded-[2px]" style:background={row.color}></span>
					{/if}
					<span class="truncate">{row.label}</span>
				</span>
				<span class={['tabular-nums', row.strong ? 'font-semibold text-fg' : 'text-fg'].join(' ')}
					>{row.value}</span
				>
			</li>
		{/each}
	</ul>
</div>
