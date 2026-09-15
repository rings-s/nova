<script>
	import Card from '../ui/Card.svelte';
	import { formatMoney, formatPercent } from '../../utils/money.js';

	/**
	 * @type {{ kpi: import('../../api/analytics.js').Kpi, currency?: string, locale?: 'en'|'ar' }}
	 */
	let { kpi, currency = 'SAR', locale = 'en' } = $props();

	let displayValue = $derived.by(() => {
		if (kpi.suppressed || kpi.value === null) return null;
		if (kpi.unit === 'currency') return formatMoney(kpi.value, currency, locale);
		if (kpi.unit === 'percent') return formatPercent(kpi.value, { locale });
		return new Intl.NumberFormat(locale === 'ar' ? 'ar-SA' : 'en-US').format(Number(kpi.value));
	});
</script>

<Card padding="sm">
	<p class="text-sm text-slate-500 dark:text-slate-400">{kpi.metric.replaceAll('_', ' ')}</p>
	{#if displayValue === null}
		<p class="mt-1 text-sm text-slate-400 dark:text-slate-500">
			Not enough data ({kpi.sample_size})
		</p>
	{:else}
		<p class="mt-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">{displayValue}</p>
	{/if}
</Card>
