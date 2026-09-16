<script>
	import Card from '../ui/Card.svelte';
	import Badge from '../ui/Badge.svelte';
	import Alert from '../ui/Alert.svelte';
	import { formatMoney } from '../../utils/money.js';
	import { formatDate } from '../../utils/datetime.js';

	/**
	 * @type {{ subscription: import('../../api/billing.js').Subscription, locale?: 'en'|'ar' }}
	 */
	let { subscription, locale = 'en' } = $props();

	/** @type {Record<string, 'neutral'|'success'|'warning'|'error'|'info'|'accent'>} */
	const statusTone = {
		trialing: 'info',
		active: 'success',
		past_due: 'warning',
		cancelled: 'neutral'
	};
</script>

<Card>
	<div class="flex items-center justify-between">
		<h3 class="text-lg font-semibold text-slate-900 capitalize dark:text-slate-100">
			{subscription.tier} plan
		</h3>
		<Badge tone={statusTone[subscription.status] ?? 'neutral'}>{subscription.status}</Badge>
	</div>
	<p class="mt-2 text-sm text-slate-500 dark:text-slate-400">
		{formatDate(subscription.current_period_start, locale)} – {formatDate(
			subscription.current_period_end,
			locale
		)}
	</p>
	<p class="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100">
		{formatMoney(subscription.monthly_amount, subscription.currency, locale)}
		<span class="text-sm font-normal text-slate-500 dark:text-slate-400">/ month</span>
	</p>
	<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">
		{subscription.seats} seat{subscription.seats === 1 ? '' : 's'} · {subscription.locations} location{subscription.locations ===
		1
			? ''
			: 's'}
	</p>
	{#if subscription.cancel_at_period_end}
		<Alert tone="warning" class="mt-3">Cancels at the end of the current period.</Alert>
	{/if}
	{#if subscription.marketplace_listing_hidden}
		<Alert tone="error" class="mt-3">
			The marketplace listing is hidden for non-payment. Calendar, queue and existing bookings keep
			working.
		</Alert>
	{/if}
</Card>
