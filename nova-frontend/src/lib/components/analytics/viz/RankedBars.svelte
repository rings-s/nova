<script>
	/**
	 * A ranked comparison (revenue by service, by provider...): one row per
	 * item, largest first, the label above a thin bar and the value at its
	 * tip, so every number is readable without hovering. Past `limit` rows,
	 * the rest fold into one "Other" row rather than shrinking every bar.
	 */
	import { formatValue } from './format.js';

	/**
	 * @type {{
	 *   model: import('../../../utils/chartData.js').RankedModel,
	 *   currency?: string,
	 *   limit?: number
	 * }}
	 */
	let { model, currency = 'SAR', limit = 6 } = $props();

	let rows = $derived.by(() => {
		if (model.rows.length <= limit) return model.rows;
		const rest = model.rows.slice(limit - 1);
		return [
			...model.rows.slice(0, limit - 1),
			{
				label: `Other (${rest.length})`,
				value: rest.reduce((sum, row) => sum + row.value, 0),
				other: true
			}
		];
	});
	let max = $derived(Math.max(1, ...rows.map((row) => row.value)));
	let total = $derived(model.rows.reduce((sum, row) => sum + row.value, 0));
</script>

<ol class="flex flex-col gap-3.5">
	{#each rows as row, i (row.label)}
		<li class="group">
			<div class="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
				<span class="flex min-w-0 items-baseline gap-2">
					<span class="w-4 shrink-0 text-xs text-fg-subtle tabular-nums">{i + 1}</span>
					<span class="truncate text-fg-secondary" title={row.label}>{row.label}</span>
				</span>
				<span class="shrink-0 font-medium text-fg tabular-nums">
					{formatValue(row.value, model.unit, { currency })}
					{#if total > 0}
						<span class="ms-1 text-xs font-normal text-fg-subtle"
							>{Math.round((row.value / total) * 100)}%</span
						>
					{/if}
				</span>
			</div>
			<div class="ms-6 h-2.5 overflow-hidden rounded-e-[4px]">
				<div
					class="h-full rounded-e-[4px] transition-[width,opacity] duration-slow ease-out-premium group-hover:opacity-85"
					style:width={`${Math.max(row.value > 0 ? 1 : 0, (row.value / max) * 100)}%`}
					style:background={'other' in row ? 'var(--chart-muted)' : 'var(--chart-series-1)'}
				></div>
			</div>
		</li>
	{/each}
</ol>
