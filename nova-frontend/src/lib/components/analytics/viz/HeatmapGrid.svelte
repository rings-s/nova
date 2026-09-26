<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * A matrix of cells shaded by magnitude in one hue (`HEAT_RAMP`, stepped
	 * per theme), with a scale legend. Zero and missing cells are drawn as the
	 * sunken surface, not as the ramp's lightest step, so "nothing happened"
	 * never reads as "a little happened". Each cell has its own tooltip.
	 */
	import { HEAT_RAMP } from '../../../utils/chartData.js';
	import Tooltip from './Tooltip.svelte';
	import { formatCategory, formatMonth, formatValue } from './format.js';

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

	let cohorts = $derived(model.rowTitle === 'First visit');
	/** @param {string} row */
	const rowLabel = (row) => (cohorts ? formatMonth(row) : formatCategory(row));

	/** A small matrix (cohorts) has room to print each value in its cell. */
	let labelled = $derived(model.columns.length <= 12);

	/** Dark ink on the light steps, light ink on the strong ones, in either theme. */
	/** @param {number|null} value */
	function inkFor(value) {
		const strong = (value ?? 0) / (model.max || 1) >= 0.57;
		return strong ? 'text-white dark:text-slate-900' : 'text-slate-900 dark:text-white';
	}

	/** @param {number|null} value */
	function fill(value) {
		if (value === null || value <= 0 || model.max <= 0) return null;
		const index = Math.min(
			HEAT_RAMP.length - 1,
			Math.floor((value / model.max) * HEAT_RAMP.length)
		);
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
			title: `${rowLabel(model.rows[hover.r])} · ${cohorts ? t('month {n}', { n: model.columns[hover.c] }) : model.columns[hover.c]}`,
			rows: [
				{
					label: model.unit === 'percent' ? t('Returned') : t('Bookings'),
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
			aria-label={t('{rows} by {columns}; the table view lists every value.', {
				rows: t(model.rowTitle),
				columns: t(model.columnTitle)
			})}
			onpointerleave={() => (hover = null)}
		>
			{#each model.rows as row, r (row)}
				<span class="flex items-center pe-2 whitespace-nowrap">{rowLabel(row)}</span>
				{#each model.columns as column, c (column)}
					{@const color = fill(model.values[r][c])}
					<span
						role="presentation"
						class={[
							'flex h-7 items-center justify-center rounded-[3px] text-[10px] font-medium tabular-nums transition-[outline-color] duration-fast',
							labelled && color ? inkFor(model.values[r][c]) : '',
							color ? '' : 'bg-surface-sunken',
							hover?.r === r && hover?.c === c ? 'outline-2 outline-offset-1 outline-fg' : ''
						].join(' ')}
						style:background={color}
						onpointerenter={(event) => enter(event, r, c)}
						>{labelled && color
							? formatValue(model.values[r][c], model.unit, { currency })
							: ''}</span
					>
				{/each}
			{/each}
			<span></span>
			{#each model.columns as column, c (column)}
				<span class="pt-1 text-center">{c % columnStep === 0 ? column.replace(':00', '') : ''}</span
				>
			{/each}
		</div>
		{#if tip}
			<Tooltip {width} {...tip} />
		{/if}
	</div>
	<div class="flex flex-wrap items-center gap-2 text-[11px] text-fg-subtle">
		{#if cohorts}
			<span class="me-3 font-medium text-fg-muted"
				>{t('Columns: months since the first visit')}</span
			>
		{/if}
		<span>{model.columnTitle === 'Hour' ? t('Quiet') : t('Fewer')}</span>
		<span class="flex gap-[3px]">
			<span class="size-3 rounded-[3px] bg-surface-sunken"></span>
			{#each HEAT_RAMP as color (color)}
				<span class="size-3 rounded-[3px]" style:background={color}></span>
			{/each}
		</span>
		<span>{model.columnTitle === 'Hour' ? t('Busy') : t('More')}</span>
		<span class="ms-auto tabular-nums"
			>{t('Peak {value}', { value: formatValue(model.max, model.unit, { currency }) })}</span
		>
	</div>
</div>
