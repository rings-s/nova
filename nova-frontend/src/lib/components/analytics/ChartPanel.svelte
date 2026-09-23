<script>
	/**
	 * One chart from the catalog (docs/13 section 7): fetches it, reads the
	 * Plotly figure into a chart model (`chartData.js`) and draws it with the
	 * analytics chart kit (`./viz`). The header comes from the catalog entry,
	 * so it is on screen before the data is.
	 *
	 * - A refetch (a new date range) keeps the previous chart, dimmed, until
	 *   the new one arrives, rather than collapsing to a skeleton.
	 * - Every chart has a table view with the same numbers.
	 * - `insufficient_data` (the forecast needs 8 complete weeks) and an empty
	 *   window are expected states, shown quietly rather than as errors.
	 * - A plan-gated chart the business's plan lacks renders locked, without
	 *   a request that would only 403.
	 */
	import { resolve } from '$app/paths';
	import { getChart } from '../../api/analytics.js';
	import { ApiError } from '../../api/client.js';
	import { chartModel, hasData, tableOf } from '../../utils/chartData.js';
	import { errorMessage } from '../../utils/errors.js';
	import Skeleton from '../ui/Skeleton.svelte';
	import Alert from '../ui/Alert.svelte';
	import Icon from '../ui/Icon.svelte';
	import ColumnChart from './viz/ColumnChart.svelte';
	import LineChart from './viz/LineChart.svelte';
	import RankedBars from './viz/RankedBars.svelte';
	import PartsBar from './viz/PartsBar.svelte';
	import HeatmapGrid from './viz/HeatmapGrid.svelte';
	import { formatCategory, formatValue } from './viz/format.js';

	/**
	 * @type {{
	 *   tenantId: string,
	 *   businessId: string,
	 *   entry: import('../../api/analytics.js').ChartCatalogEntry,
	 *   dateFrom?: string|null,
	 *   dateTo?: string|null,
	 *   currency?: string,
	 *   locked?: boolean,
	 *   class?: string
	 * }}
	 */
	let {
		tenantId,
		businessId,
		entry,
		dateFrom = null,
		dateTo = null,
		currency = 'SAR',
		locked = false,
		class: className = ''
	} = $props();

	const uid = $props.id();

	let loading = $state(true);
	let error = $state(/** @type {string|null} */ (null));
	let errorIsExpected = $state(false);
	let chart = $state(/** @type {import('../../api/analytics.js').Chart|null} */ (null));
	let showTable = $state(false);

	$effect(() => {
		if (locked) return;
		const params = { businessId, dateFrom, dateTo };
		let cancelled = false;
		loading = true;
		getChart(tenantId, entry.chart_id, params)
			.then((result) => {
				if (cancelled) return;
				chart = result;
				error = null;
			})
			.catch((err) => {
				if (cancelled) return;
				error = errorMessage(err);
				errorIsExpected = err instanceof ApiError && err.code === 'insufficient_data';
			})
			.finally(() => {
				if (!cancelled) loading = false;
			});
		return () => {
			cancelled = true;
		};
	});

	let model = $derived(chart ? chartModel(chart) : null);
	let empty = $derived(model ? !hasData(model) : false);

	/** Series that need a legend: two or more sharing one plot. */
	let legend = $derived.by(() => {
		if (!model) return [];
		if (model.type === 'columns' && model.series.length > 1) return model.series;
		if (model.type === 'combo') return [...model.columns.series, ...model.line.series];
		return [];
	});

	let table = $derived(
		model
			? tableOf(
					model,
					(value, unit) => formatValue(value, unit, { currency }),
					(category) => formatCategory(category)
				)
			: null
	);
</script>

<section
	class={[
		'flex min-w-0 flex-col rounded-card border border-line bg-surface p-5 shadow-card',
		className
	].join(' ')}
	aria-labelledby={`${uid}-title`}
>
	<header class="mb-4 flex items-start justify-between gap-3">
		<div class="min-w-0">
			<h3 id={`${uid}-title`} class="flex items-center gap-2 text-sm font-semibold text-fg">
				{entry.title_en}
				{#if locked}<Icon name="lock" class="size-3.5 text-fg-subtle" />{/if}
			</h3>
			<p class="mt-0.5 text-[13px] text-fg-muted">{entry.question_en}</p>
		</div>
		{#if model && !empty && !locked}
			<button
				type="button"
				class={[
					'flex size-8 shrink-0 items-center justify-center rounded-control focus-ring transition-colors duration-fast',
					showTable ? 'bg-accent-soft text-accent' : 'text-fg-subtle hover:bg-surface-muted hover:text-fg'
				].join(' ')}
				aria-pressed={showTable}
				aria-label={showTable ? 'Show chart' : 'Show as table'}
				title={showTable ? 'Show chart' : 'Show as table'}
				onclick={() => (showTable = !showTable)}
			>
				<Icon name={showTable ? 'chart-bar' : 'table'} class="size-4" />
			</button>
		{/if}
	</header>

	{#if locked}
		<div class="relative flex min-h-48 flex-1 items-center justify-center overflow-hidden rounded-control">
			<div class="absolute inset-0 flex items-end gap-2 px-4 pb-3 opacity-40 blur-[2px]" aria-hidden="true">
				{#each [38, 62, 45, 80, 56, 70, 48, 90, 64, 52] as h, i (i)}
					<div class="flex-1 rounded-t-[4px] bg-line-strong" style:height={`${h}%`}></div>
				{/each}
			</div>
			<div class="relative flex flex-col items-center gap-2 rounded-card border border-line bg-surface/90 px-5 py-4 text-center shadow-raised backdrop-blur">
				<span class="flex size-9 items-center justify-center rounded-full bg-accent-soft text-accent">
					<Icon name="lock" class="size-4" />
				</span>
				<p class="text-sm font-medium text-fg">Not in your current plan</p>
				<a href={resolve('/app/billing')} class="text-sm font-semibold text-accent hover:underline">
					See plans
				</a>
			</div>
		</div>
	{:else if loading && !chart}
		<Skeleton class="h-56 w-full rounded-control" />
	{:else if error && !chart}
		{#if errorIsExpected}
			<div class="flex min-h-48 flex-1 flex-col items-center justify-center gap-2 rounded-control bg-surface-sunken p-6 text-center">
				<Icon name="clock" class="size-5 text-fg-subtle" />
				<p class="max-w-xs text-sm text-fg-muted">{error}</p>
			</div>
		{:else}
			<Alert tone="error">{error}</Alert>
		{/if}
	{:else if model}
		<div
			class={['flex flex-1 flex-col transition-opacity duration-base', loading ? 'opacity-50' : ''].join(' ')}
			aria-busy={loading}
		>
			{#if empty}
				<div class="flex min-h-48 flex-1 flex-col items-center justify-center gap-2 rounded-control bg-surface-sunken p-6 text-center">
					<Icon name="chart-bar" class="size-5 text-fg-subtle" />
					<p class="text-sm text-fg-muted">Nothing in this window yet.</p>
				</div>
			{:else if showTable && table}
				<div class="max-h-72 overflow-auto rounded-control border border-line-subtle">
					<table class="w-full text-[13px]">
						<thead class="sticky top-0 bg-surface-sunken">
							<tr>
								{#each table.head as cell, i (i)}
									<th
										scope="col"
										class={['px-3 py-2 font-medium whitespace-nowrap text-fg-muted', i ? 'text-end' : 'text-start'].join(' ')}
										>{cell}</th
									>
								{/each}
							</tr>
						</thead>
						<tbody class="divide-y divide-line-subtle">
							{#each table.rows as row, r (r)}
								<tr>
									{#each row as cell, i (i)}
										{#if i === 0}
											<th scope="row" class="px-3 py-1.5 text-start font-normal whitespace-nowrap text-fg-secondary">{cell}</th>
										{:else}
											<td class="px-3 py-1.5 text-end text-fg tabular-nums">{cell}</td>
										{/if}
									{/each}
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{:else}
				{#if legend.length}
					<ul class="mb-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-fg-secondary">
						{#each legend as series (series.label)}
							<li class="flex items-center gap-1.5">
								<span class="size-2.5 rounded-[3px]" style:background={series.color}></span>
								{series.label}
							</li>
						{/each}
					</ul>
				{/if}
				{#if model.type === 'columns'}
					<ColumnChart {model} {currency} label={entry.title_en} />
				{:else if model.type === 'line'}
					<LineChart {model} {currency} label={entry.title_en} />
				{:else if model.type === 'combo'}
					<!-- Two measures on one x axis: two charts, never one chart with two y-axes. -->
					<ColumnChart
						model={model.columns}
						{currency}
						height={150}
						showXAxis={false}
						label={model.columns.series[0]?.label}
					/>
					<p class="mt-3 mb-1 text-xs font-medium text-fg-muted">{model.line.series[0]?.label}</p>
					<LineChart model={model.line} {currency} height={130} label={model.line.series[0]?.label} />
				{:else if model.type === 'ranked'}
					<RankedBars {model} {currency} />
				{:else if model.type === 'parts'}
					<PartsBar {model} {currency} />
				{:else if model.type === 'heatmap'}
					<HeatmapGrid {model} {currency} />
				{/if}
			{/if}
		</div>
	{:else}
		<Alert tone="warning">This chart can't be shown here yet.</Alert>
	{/if}
</section>
