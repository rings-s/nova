<script>
	import Card from '../ui/Card.svelte';
	import Badge from '../ui/Badge.svelte';
	import Alert from '../ui/Alert.svelte';
	import { formatMoney } from '../../utils/money.js';
	import { formatDate } from '../../utils/datetime.js';

	/**
	 * @type {{
	 *   subscription: import('../../api/billing.js').Subscription,
	 *   locale?: 'en'|'ar',
	 *   actions?: import('svelte').Snippet
	 * }}
	 */
	let { subscription, locale = 'en', actions } = $props();

	/** @type {Record<string, 'neutral'|'success'|'warning'|'error'|'info'|'accent'>} */
	const statusTone = {
		trialing: 'info',
		active: 'success',
		past_due: 'warning',
		cancelled: 'neutral'
	};
</script>

<Card padding="none">
	<div class="grid gap-6 p-6 sm:grid-cols-[1fr_auto]">
		<div>
			<div class="flex flex-wrap items-center gap-2">
				<p class="text-xs font-semibold tracking-wider text-accent uppercase">Current plan</p>
				<Badge tone={statusTone[subscription.status] ?? 'neutral'} size="sm" dot>
					{subscription.status.replaceAll('_', ' ')}
				</Badge>
			</div>
			<h2 class="mt-1 text-2xl font-semibold tracking-tight text-fg capitalize">
				{subscription.tier}
			</h2>
			<p class="mt-3 text-3xl font-semibold tracking-tight text-fg tabular-nums">
				{formatMoney(subscription.monthly_amount, subscription.currency, locale)}
				<span class="text-sm font-normal text-fg-muted">/ month</span>
			</p>
		</div>
		<dl class="grid grid-cols-3 gap-4 self-end text-sm sm:grid-cols-1 sm:gap-2 sm:text-end">
			<div>
				<dt class="text-xs text-fg-muted">Billing period</dt>
				<dd class="font-medium text-fg">
					{formatDate(subscription.current_period_start, locale)} – {formatDate(
						subscription.current_period_end,
						locale
					)}
				</dd>
			</div>
			<div>
				<dt class="text-xs text-fg-muted">Seats</dt>
				<dd class="font-medium text-fg tabular-nums">{subscription.seats}</dd>
			</div>
			<div>
				<dt class="text-xs text-fg-muted">Locations</dt>
				<dd class="font-medium text-fg tabular-nums">{subscription.locations}</dd>
			</div>
		</dl>
	</div>
	{#if subscription.cancel_at_period_end || subscription.marketplace_listing_hidden}
		<div class="flex flex-col gap-3 px-6 pb-6">
			{#if subscription.cancel_at_period_end}
				<Alert tone="warning">Cancels at the end of the current period.</Alert>
			{/if}
			{#if subscription.marketplace_listing_hidden}
				<Alert tone="error">
					The marketplace listing is hidden for non-payment. Calendar, queue and existing bookings
					keep working.
				</Alert>
			{/if}
		</div>
	{/if}
	{#if actions}
		<div
			class="flex flex-wrap justify-end gap-2 rounded-b-card border-t border-line bg-surface-sunken px-6 py-3"
		>
			{@render actions()}
		</div>
	{/if}
</Card>
