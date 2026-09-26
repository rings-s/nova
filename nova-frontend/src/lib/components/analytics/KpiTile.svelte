<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * One KPI: label, value, and its change against the previous window of the
	 * same length. The change carries an arrow and words as well as colour,
	 * and is coloured by whether it is good for this metric (fewer no-shows is
	 * green), not by its sign.
	 */
	import Icon from '../ui/Icon.svelte';
	import { formatKpi, kpiDelta, kpiMeta } from './kpis.js';

	/**
	 * @type {{
	 *   kpi: import('../../api/analytics.js').Kpi|undefined,
	 *   previous?: import('../../api/analytics.js').Kpi|undefined,
	 *   currency?: string,
	 *   compareLabel?: string,
	 *   size?: 'md'|'sm'
	 * }}
	 */
	let { kpi, previous, currency = 'SAR', compareLabel = '', size = 'md' } = $props();

	let meta = $derived(kpiMeta(kpi?.metric ?? ''));
	let value = $derived(formatKpi(kpi, { currency, compact: true }));
	let delta = $derived(kpiDelta(kpi, previous));
</script>

<div class={['flex min-w-0 flex-col', size === 'md' ? 'gap-1.5' : 'gap-1'].join(' ')}>
	<p class="truncate text-[13px] font-medium text-fg-muted" title={t(meta.label)}>
		{t(meta.label)}
	</p>
	{#if value === null}
		<p class={['font-semibold text-fg-subtle', size === 'md' ? 'text-3xl' : 'text-xl'].join(' ')}>
			—
		</p>
		<p class="text-xs text-fg-subtle">{t('Too few bookings to tell yet')}</p>
	{:else}
		<p
			class={[
				'truncate font-semibold tracking-tight text-fg',
				size === 'md' ? 'text-3xl' : 'text-xl'
			].join(' ')}
			title={value}
		>
			{value}
		</p>
		{#if delta}
			<p class="flex flex-wrap items-center gap-x-1.5 text-xs">
				<span
					class={[
						'inline-flex items-center gap-0.5 font-medium',
						delta.tone === 'good'
							? 'text-emerald-700 dark:text-emerald-400'
							: delta.tone === 'bad'
								? 'text-rose-700 dark:text-rose-400'
								: 'text-fg-muted'
					].join(' ')}
				>
					<Icon
						name={delta.direction > 0 ? 'arrow-up' : delta.direction < 0 ? 'arrow-down' : 'minus'}
						class="size-3"
					/>
					{delta.text}
				</span>
				{#if compareLabel}<span class="text-fg-subtle">{compareLabel}</span>{/if}
			</p>
		{:else if meta.hint}
			<p class="truncate text-xs text-fg-subtle">{t(meta.hint)}</p>
		{/if}
	{/if}
</div>
