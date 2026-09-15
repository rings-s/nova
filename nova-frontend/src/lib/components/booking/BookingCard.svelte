<script>
	import Card from '../ui/Card.svelte';
	import { formatDateTime } from '../../utils/datetime.js';
	import { formatMoney } from '../../utils/money.js';
	import BookingStatusBadge from './BookingStatusBadge.svelte';

	/**
	 * @type {{
	 *   booking: import('../../api/booking.js').Booking,
	 *   locale?: 'en'|'ar',
	 *   actions?: import('svelte').Snippet
	 * }}
	 */
	let { booking, locale = 'en', actions } = $props();
</script>

<Card padding="sm">
	<div class="flex items-start justify-between gap-3">
		<div>
			<p class="font-medium text-slate-900 dark:text-slate-100">
				{formatDateTime(booking.starts_at, locale)}
			</p>
			<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">
				{formatMoney(booking.price, booking.currency, locale)} · {booking.source}
			</p>
			{#if booking.notes}
				<p class="mt-1 text-sm text-slate-600 dark:text-slate-300">{booking.notes}</p>
			{/if}
			{#if booking.status === 'cancelled' && booking.cancellation_reason}
				<p class="mt-1 text-sm text-red-600">{booking.cancellation_reason}</p>
			{/if}
		</div>
		<BookingStatusBadge status={booking.status} />
	</div>
	{#if actions}
		<div class="mt-3 flex gap-2">{@render actions()}</div>
	{/if}
</Card>
