<script>
	import Card from '../ui/Card.svelte';
	import { formatMoney, formatPercent } from '../../utils/money.js';

	/**
	 * @type {{ kpi: import('../../api/analytics.js').Kpi, currency?: string, locale?: 'en'|'ar' }}
	 */
	let { kpi, currency = 'SAR', locale = 'en' } = $props();

	let label = $derived(kpi.metric.replaceAll('_', ' '));

	let displayValue = $derived.by(() => {
		if (kpi.suppressed || kpi.value === null) return null;
		if (kpi.unit === 'currency') return formatMoney(kpi.value, currency, locale);
		if (kpi.unit === 'percent') return formatPercent(kpi.value, { locale });
		return new Intl.NumberFormat(locale === 'ar' ? 'ar-SA' : 'en-US').format(Number(kpi.value));
	});
</script>

<Card padding="sm" class="min-w-0">
	<p class="truncate text-[13px] font-medium text-fg-muted first-letter:uppercase" title={label}>
		{label}
	</p>
	{#if displayValue === null}
		<p class="mt-1.5 text-2xl font-semibold text-fg-subtle">—</p>
		<p class="mt-0.5 text-xs text-fg-subtle">Not enough data yet</p>
	{:else}
		<p class="mt-1.5 text-2xl font-semibold tracking-tight text-fg tabular-nums">{displayValue}</p>
	{/if}
</Card>
