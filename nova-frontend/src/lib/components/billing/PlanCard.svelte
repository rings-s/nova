<script>
	import Card from '../ui/Card.svelte';
	import Icon from '../ui/Icon.svelte';
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

<Card
	padding="none"
	class={`relative flex h-full flex-col ${current ? 'border-brand-500 ring-4 ring-brand-500/15' : ''}`}
>
	<div class="flex flex-1 flex-col p-6">
		<div class="flex items-center justify-between gap-2">
			<h3 class="text-base font-semibold text-fg capitalize">{plan.tier}</h3>
			{#if current}<Badge tone="accent" size="sm">Current</Badge>{/if}
		</div>
		<p class="mt-4 text-3xl font-semibold tracking-tight text-fg tabular-nums">
			{formatMoney(price, plan.currency, locale)}
		</p>
		<p class="mt-1 text-xs text-fg-muted">
			per {annual ? 'year' : 'month'}{plan.priced_per_location ? ', per location' : ''}
		</p>
		<p class="mt-4 rounded-control bg-surface-sunken px-3 py-2 text-xs text-fg-secondary">
			<span class="font-semibold text-fg">
				{formatPercent(plan.new_client_commission_pct, { locale })}
			</span>
			commission on new marketplace clients
		</p>
		{#if plan.included_features.length > 0}
			<ul class="mt-5 flex flex-col gap-2 text-sm text-fg-secondary">
				{#each plan.included_features as feature (feature)}
					<li class="flex items-start gap-2 first-letter:uppercase">
						<Icon name="check" class="mt-0.5 size-4 text-emerald-600 dark:text-emerald-400" />
						<span class="first-letter:uppercase">{feature.replaceAll('_', ' ')}</span>
					</li>
				{/each}
			</ul>
		{/if}
		{#if onselect}
			<div class="mt-auto pt-6">
				<Button fullWidth variant={current ? 'outline' : 'primary'} onclick={() => onselect(plan)}>
					{current ? 'Manage plan' : 'Choose plan'}
				</Button>
			</div>
		{/if}
	</div>
</Card>
