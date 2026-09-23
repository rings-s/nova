<script>
	/**
	 * A matrix of cells shaded by magnitude in one hue (`HEAT_RAMP`, stepped
	 * per theme), with a scale legend. Zero and missing cells are drawn as the
	 * sunken surface, not as the ramp's lightest step, so "nothing happened"
	 * never reads as "a little happened". Each cell has its own tooltip.
	 */
	import { HEAT_RAMP } from '../../../utils/chartData.js';
	import Tooltip from './Tooltip.svelte';
	import { formatCategory, formatValue } from './format.js';

	/**
	 * @type {{
	 *   model: import('../../../utils/chartData.js').HeatmapModel,
	 *   currency?: string
	 * }}
	 */
	let { model, currency = 'SAR' } = $props();

	let width = $state(0);
	let hover = $state(/** @type {{ r: number, c: number, x: number, y: number }|null} */ (null));

	/** Wide matrices (hours of the day) label every third column. */
	let columnStep = $derived(model.columns.length > 12 ? 3 : 1);

	/** @param {number|null} value */
	function fill(value) {
		if (value === null || value <= 0 || model.max <= 0) return null;
		const index = Math.min(HEAT_RAMP.length - 1, Math.floor((value / model.max) * HEAT_RAMP.length));
		return HEAT_RAMP[index];
	}

	/** @param {PointerEvent} event @param {number} r @param {number} c */
	function enter(event, r, c) {
		const cell = /** @type {HTMLElement} */ (event.currentTarget);
		const box = /** @type {HTMLElement} */ (cell.offsetParent);
		const a = cell.getBoundingClientRect();
		const b = box.getBoundingClientRect();
		hover = { r, c, x: a.left - b.left + a.width / 2, y: a.bottom - b.top + 4 };
	}

	let tip = $derived.by(() => {
		if (!hover) return null;
		return {
			x: hover.x,
			y: hover.y,
			title: `${formatCategory(model.rows[hover.r])} · ${model.columnTitle} ${model.columns[hover.c]}`,
			rows: [
				{
					label: model.unit === 'percent' ? 'Returned' : 'Bookings',
					value: formatValue(model.values[hover.r][hover.c], model.unit, { currency }),
					strong: true
				}
			]
		};
	});
</script>

<div class="flex flex-col gap-4">
	<div class="relative overflow-x-auto" bind:clientWidth={width}>
		<div
			class="grid min-w-[520px] gap-[3px] text-[11px] text-fg-subtle"
			style:grid-template-columns={`auto repeat(${model.columns.length}, minmax(0, 1fr))`}
			role="img"
			aria-label={`${model.rowTitle} by ${model.columnTitle}; the table view lists every value.`}
			onpointerleave={() => (hover = null)}
		>
			{#each model.rows as row, r (row)}
				<span class="flex items-center pe-2 whitespace-nowrap">{formatCategory(row)}</span>
				{#each model.columns as column, c (column)}
					{@const color = fill(model.values[r][c])}
					<span
						role="presentation"
						class={[
							'aspect-square min-h-3 rounded-[3px] transition-[outline-color] duration-fast',
							color ? '' : 'bg-surface-sunken',
							hover?.r === r && hover?.c === c ? 'outline-2 outline-offset-1 outline-fg' : ''
						].join(' ')}
						style:background={color}
						onpointerenter={(event) => enter(event, r, c)}
					></span>
				{/each}
			{/each}
			<span></span>
			{#each model.columns as column, c (column)}
				<span class="pt-1 text-center">{c % columnStep === 0 ? column.replace(':00', '') : ''}</span>
			{/each}
		</div>
		{#if tip}
			<Tooltip {width} {...tip} />
		{/if}
	</div>
	<div class="flex items-center gap-2 text-[11px] text-fg-subtle">
		<span>{model.columnTitle === 'Hour' ? 'Quiet' : 'Fewer'}</span>
		<span class="flex gap-[3px]">
			<span class="size-3 rounded-[3px] bg-surface-sunken"></span>
			{#each HEAT_RAMP as color (color)}
				<span class="size-3 rounded-[3px]" style:background={color}></span>
			{/each}
		</span>
		<span>{model.columnTitle === 'Hour' ? 'Busy' : 'More'}</span>
		<span class="ms-auto tabular-nums">Peak {formatValue(model.max, model.unit, { currency })}</span>
	</div>
</div>
