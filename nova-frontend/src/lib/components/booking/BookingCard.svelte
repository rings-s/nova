<script>
	import { formatDate, formatTime } from '../../utils/datetime.js';
	import { formatMoney } from '../../utils/money.js';
	import Icon from '../ui/Icon.svelte';
	import BookingStatusBadge from './BookingStatusBadge.svelte';

	/**
	 * One appointment: a time block on the leading edge (so a day sheet reads
	 * as a schedule), the details, its status, and whatever actions the
	 * caller allows for that status.
	 *
	 * @type {{
	 *   booking: import('../../api/booking.js').Booking,
	 *   locale?: 'en'|'ar',
	 *   title?: string|null,
	 *   actions?: import('svelte').Snippet
	 * }}
	 */
	let { booking, locale = 'en', title = null, actions } = $props();

	const sourceLabel = /** @type {Record<string, string>} */ ({
		marketplace: 'Marketplace',
		direct_link: 'Direct link',
		whatsapp: 'WhatsApp',
		walk_in: 'Walk-in',
		reception: 'Reception',
		ai_agent: 'AI assistant'
	});

	let muted = $derived(booking.status === 'cancelled' || booking.status === 'no_show');
</script>

<article
	class="flex flex-col gap-4 rounded-card border border-line bg-surface p-4 shadow-card sm:flex-row sm:items-center"
>
	<div class="flex items-center gap-4 sm:w-40 sm:shrink-0">
		<div
			class={`flex min-w-20 shrink-0 flex-col items-center rounded-control border px-2 py-1.5 text-center whitespace-nowrap ${muted ? 'border-line bg-surface-sunken' : 'border-brand-200 bg-accent-soft dark:border-brand-500/20'}`}
		>
			<span
				class={`text-sm font-semibold tabular-nums ${muted ? 'text-fg-muted line-through' : 'text-accent'}`}
			>
				{formatTime(booking.starts_at, locale)}
			</span>
			<span class="text-[11px] text-fg-muted tabular-nums"
				>{formatTime(booking.ends_at, locale)}</span
			>
		</div>
		<p class="text-xs text-fg-muted sm:hidden">{formatDate(booking.starts_at, locale)}</p>
	</div>

	<div class="min-w-0 flex-1">
		<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
			<p class="font-semibold text-fg">{title ?? formatDate(booking.starts_at, locale)}</p>
			<BookingStatusBadge status={booking.status} />
		</div>
		<p class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-fg-muted">
			<span class="font-medium text-fg-secondary tabular-nums">
				{formatMoney(booking.price, booking.currency, locale)}
			</span>
			<span class="inline-flex items-center gap-1">
				<Icon name="globe" class="size-3.5" />
				{sourceLabel[booking.source] ?? booking.source}
			</span>
		</p>
		{#if booking.notes}
			<p class="mt-2 rounded-control bg-surface-sunken px-3 py-2 text-sm text-fg-secondary">
				{booking.notes}
			</p>
		{/if}
		{#if booking.status === 'cancelled' && booking.cancellation_reason}
			<p class="mt-2 text-sm text-red-600 dark:text-red-400">{booking.cancellation_reason}</p>
		{/if}
	</div>

	{#if actions}
		<div class="flex flex-wrap gap-2 sm:justify-end">{@render actions()}</div>
	{/if}
</article>
