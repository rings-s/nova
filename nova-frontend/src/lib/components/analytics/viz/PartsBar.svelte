<script>
	/**
	 * Part-to-whole as one 100% bar with a legend that carries the numbers:
	 * lengths along one line compare more accurately than a donut's angles,
	 * and a small part stays visible next to a dominant one. Segments are
	 * split by a 2px surface gap; only the bar's two outer ends are rounded.
	 */
	import Tooltip from './Tooltip.svelte';
	import { formatValue } from './format.js';

	/**
	 * @type {{
	 *   model: import('../../../utils/chartData.js').PartsModel,
	 *   currency?: string
	 * }}
	 */
	let { model, currency = 'SAR' } = $props();

	let width = $state(0);
	let hover = $state(/** @type {number|null} */ (null));
	let total = $derived(model.parts.reduce((sum, part) => sum + part.value, 0));
	/** @param {number} value */
	const share = (value) => (total ? value / total : 0);
	/** @param {number} value */
	const pct = (value) => `${Math.round(share(value) * 1000) / 10}%`;

	let lead = $derived(
		model.parts.reduce((best, part) => (part.value > best.value ? part : best), model.parts[0])
	);

	let tip = $derived.by(() => {
		if (hover === null) return null;
		const part = model.parts[hover];
		const before = model.parts.slice(0, hover).reduce((sum, p) => sum + share(p.value), 0);
		return {
			x: (before + share(part.value) / 2) * width,
			y: 40,
			title: part.label,
			rows: [
				{ label: 'Value', value: formatValue(part.value, model.unit, { currency }) },
				{ label: 'Share', value: pct(part.value), strong: true }
			]
		};
	});
</script>

<div class="flex flex-col gap-5">
	{#if lead && total > 0}
		<p class="text-sm text-fg-muted">
			<span class="text-2xl font-semibold tracking-tight text-fg">{pct(lead.value)}</span>
			<span class="ms-1">{lead.label}</span>
		</p>
	{/if}
	<div class="relative" bind:clientWidth={width}>
		<div class="flex h-4 w-full gap-0.5 overflow-hidden rounded-[4px]" role="img" aria-label={model.parts.map((p) => `${p.label} ${pct(p.value)}`).join(', ')}>
			{#each model.parts as part, i (part.label)}
				{#if part.value > 0}
					<div
						role="presentation"
						class="h-full min-w-1 transition-opacity duration-fast"
						style:flex-grow={part.value}
						style:flex-basis="0"
						style:background={part.color}
						style:opacity={hover === null || hover === i ? 1 : 0.45}
						onpointerenter={() => (hover = i)}
						onpointerleave={() => (hover = null)}
					></div>
				{/if}
			{/each}
		</div>
		{#if tip}
			<Tooltip {width} {...tip} />
		{/if}
	</div>
	<ul class="grid gap-x-6 gap-y-2.5 sm:grid-cols-2">
		{#each model.parts as part, i (part.label)}
			<li
				class="flex items-center justify-between gap-3 text-sm"
				onpointerenter={() => (hover = i)}
				onpointerleave={() => (hover = null)}
			>
				<span class="flex min-w-0 items-center gap-2 text-fg-secondary">
					<span class="size-2.5 shrink-0 rounded-[3px]" style:background={part.color}></span>
					<span class="truncate">{part.label}</span>
				</span>
				<span class="shrink-0 text-fg tabular-nums">
					{formatValue(part.value, model.unit, { currency })}
					<span class="ms-1 text-xs text-fg-subtle">{pct(part.value)}</span>
				</span>
			</li>
		{/each}
	</ul>
</div>
