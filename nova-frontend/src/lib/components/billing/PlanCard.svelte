<script>
	import Card from '../ui/Card.svelte';
	import Badge from '../ui/Badge.svelte';
	import Button from '../ui/Button.svelte';
	import { formatMoney, formatPercent } from '../../utils/money.js';

	/**
	 * @type {{
	 *   plan: import('../../api/billing.js').Plan,
	 *   locale?: 'en'|'ar',
	 *   annual?: boolean,
	 *   current?: boolean,
	 *   onselect?: (plan: import('../../api/billing.js').Plan) => void
	 * }}
	 */
	let { plan, locale = 'en', annual = false, current = false, onselect } = $props();

	let price = $derived(annual && plan.annual_price ? plan.annual_price : plan.monthly_price);
</script>

<Card class={current ? 'ring-2 ring-rose-500' : ''}>
	<div class="flex items-center justify-between">
		<h3 class="text-lg font-semibold capitalize text-slate-900 dark:text-slate-100">{plan.tier}</h3>
		{#if current}<Badge tone="accent">Current plan</Badge>{/if}
	</div>
	<p class="mt-2 text-2xl font-bold text-slate-900 dark:text-slate-100">
		{formatMoney(price, plan.currency, locale)}
		<span class="text-sm font-normal text-slate-500 dark:text-slate-400">
			/ {annual ? 'year' : 'month'}{plan.priced_per_location ? ' per location' : ''}
		</span>
	</p>
	<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">
		{formatPercent(plan.new_client_commission_pct, { locale })} commission on new marketplace clients
	</p>
	{#if plan.included_features.length > 0}
		<ul class="mt-3 flex flex-col gap-1 text-sm text-slate-600 dark:text-slate-300">
			{#each plan.included_features as feature (feature)}
				<li class="flex items-center gap-2">
					<svg class="size-4 shrink-0 text-emerald-600" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
						<path
							fill-rule="evenodd"
							d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 111.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
							clip-rule="evenodd"
						/>
					</svg>
					{feature}
				</li>
			{/each}
		</ul>
	{/if}
	{#if onselect}
		<Button class="mt-4" fullWidth variant={current ? 'outline' : 'primary'} onclick={() => onselect(plan)}>
			{current ? 'Manage plan' : 'Choose plan'}
		</Button>
	{/if}
</Card>
