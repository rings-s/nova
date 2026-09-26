<script>
	import { t, tp, m } from '$lib/i18n/index.svelte.js';
	/**
	 * The business's plan at a glance: what it is, what it costs, where the
	 * billing period is, and how much of the plan's room is in use. A plan
	 * set to cancel says the last day it covers instead of a renewal date.
	 */
	import Badge from '../ui/Badge.svelte';
	import {
		formatPrice,
		daysLeft,
		formatDay,
		lastDayOf,
		periodProgress,
		planName,
		planTagline
	} from './plans.js';

	/**
	 * @type {{
	 *   subscription: import('../../api/billing.js').Subscription,
	 *   plan?: import('../../api/billing.js').Plan|null,
	 *   actions?: import('svelte').Snippet
	 * }}
	 */
	let { subscription, plan = null, actions } = $props();

	/** @type {Record<string, { label: string, tone: 'neutral'|'success'|'warning'|'error'|'info' }>} */
	const STATUS = {
		trialing: { label: m('Trial'), tone: 'info' },
		pending_payment: { label: m('Awaiting payment'), tone: 'warning' },
		active: { label: m('Active'), tone: 'success' },
		past_due: { label: m('Payment overdue'), tone: 'error' },
		cancelled: { label: m('Cancelled'), tone: 'neutral' }
	};

	let status = $derived(
		subscription.cancel_at_period_end && subscription.status !== 'cancelled'
			? { label: m('Cancelling'), tone: /** @type {'warning'} */ ('warning') }
			: (STATUS[subscription.status] ?? { label: subscription.status, tone: 'neutral' })
	);
	let progress = $derived(
		periodProgress(subscription.current_period_start, subscription.current_period_end)
	);
	let left = $derived(daysLeft(subscription.current_period_end));
	let free = $derived(Number(subscription.monthly_amount) === 0);

	let usage = $derived([
		{ label: m('Team members'), used: subscription.seats, limit: plan?.max_seats ?? null },
		{ label: m('Branches'), used: subscription.locations, limit: plan?.max_locations ?? null }
	]);
</script>

<section
	class="flex h-full flex-col overflow-hidden rounded-panel border border-line bg-surface shadow-card"
	aria-labelledby="current-plan-heading"
>
	<div class="flex flex-1 flex-col gap-6 p-6 sm:p-7">
		<div class="flex flex-wrap items-start justify-between gap-4">
			<div>
				<p class="text-xs font-semibold tracking-wider text-fg-muted uppercase">{t('Your plan')}</p>
				<div class="mt-1.5 flex flex-wrap items-center gap-2.5">
					<h2 id="current-plan-heading" class="text-2xl font-semibold tracking-tight text-fg">
						{planName(subscription.tier)}
					</h2>
					<Badge tone={status.tone} size="sm" dot>{t(status.label)}</Badge>
				</div>
				<p class="mt-1 text-sm text-fg-muted">{planTagline(subscription.tier)}</p>
			</div>
			<div class="text-end">
				<p class="text-3xl font-semibold tracking-tight text-fg">
					{free ? t('Free') : formatPrice(subscription.monthly_amount, subscription.currency)}
				</p>
				<p class="text-xs text-fg-muted">
					{#if free}
						{t('Commission only')}
					{:else}
						{t('a month')}{subscription.annual
							? t(', billed yearly')
							: ''}{plan?.priced_per_location && subscription.locations > 1
							? ` · ${t('{count} branches', { count: subscription.locations })}`
							: ''}
					{/if}
				</p>
			</div>
		</div>

		<div>
			<div class="mb-2 flex flex-wrap items-baseline justify-between gap-2 text-sm">
				<p class="text-fg-secondary">
					{formatDay(subscription.current_period_start, { year: false })} – {formatDay(
						lastDayOf(subscription.current_period_end)
					)}
				</p>
				<p class="text-fg-muted">
					{#if subscription.status === 'cancelled'}
						{t('Ended')}
					{:else if subscription.cancel_at_period_end}
						<span class="font-medium text-fg"
							>{t('Ends {date}', {
								date: formatDay(lastDayOf(subscription.current_period_end))
							})}</span
						>
						· {tp(left, '{count} day left', '{count} days left')}
					{:else}
						{t('Renews {date}', { date: formatDay(subscription.current_period_end) })} ·
						{tp(left, '{count} day left', '{count} days left')}
					{/if}
				</p>
			</div>
			<div
				class="h-1.5 overflow-hidden rounded-full bg-surface-muted"
				role="progressbar"
				aria-label={t('Billing period elapsed')}
				aria-valuemin="0"
				aria-valuemax="100"
				aria-valuenow={Math.round(progress * 100)}
			>
				<div
					class={[
						'h-full rounded-full',
						subscription.cancel_at_period_end ? 'bg-amber-500' : 'bg-brand-500'
					].join(' ')}
					style:width={`${progress * 100}%`}
				></div>
			</div>
		</div>

		<dl class="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4">
			{#each usage as item (item.label)}
				{@const share = item.limit ? Math.min(1, item.used / item.limit) : null}
				<div class="rounded-card bg-surface-sunken p-4">
					<dt class="text-xs text-fg-muted">{t(item.label)}</dt>
					<dd class="mt-1 text-lg font-semibold text-fg">
						{item.used}
						<span class="text-sm font-normal text-fg-muted">
							{item.limit === null ? t('of unlimited') : t('of {limit}', { limit: item.limit })}
						</span>
					</dd>
					{#if share !== null}
						<div class="mt-2 h-1 overflow-hidden rounded-full bg-surface-muted">
							<div
								class={['h-full rounded-full', share >= 1 ? 'bg-amber-500' : 'bg-fg-subtle'].join(
									' '
								)}
								style:width={`${share * 100}%`}
							></div>
						</div>
					{/if}
				</div>
			{/each}
			{#if plan}
				<div class="col-span-2 rounded-card bg-surface-sunken p-4 sm:col-span-1">
					<dt class="text-xs text-fg-muted">{t('Commission on new clients')}</dt>
					<dd class="mt-1 text-lg font-semibold text-fg">
						{Number(plan.new_client_commission_pct)}%
					</dd>
					<p class="mt-1 text-xs text-fg-muted">
						{Number(plan.repeat_commission_pct)
							? t('{percent}% on returning', { percent: Number(plan.repeat_commission_pct) })
							: t('None on returning clients')}
					</p>
				</div>
			{/if}
		</dl>
	</div>

	{#if actions}
		<div
			class="flex flex-wrap items-center justify-end gap-2 border-t border-line bg-surface-sunken px-6 py-3 sm:px-7"
		>
			{@render actions()}
		</div>
	{/if}
</section>
