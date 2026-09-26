<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * A booking's check-in ticket: the QR the customer shows at the counter,
	 * the short code reception can read out, and when it stops working.
	 *
	 * Used by the chat (a booking an agent just made) and by My bookings.
	 */
	import { formatDateTime } from '../../utils/datetime.js';
	import BookingStatusBadge from '../booking/BookingStatusBadge.svelte';
	import TicketQr from './TicketQr.svelte';

	/**
	 * @type {{
	 *   qrPayload: string,
	 *   ticketCode: string,
	 *   startsAt: string,
	 *   expiresAt: string,
	 *   businessName?: string|null,
	 *   status?: import('../../api/booking.js').BookingStatus|null,
	 *   class?: string
	 * }}
	 */
	let {
		qrPayload,
		ticketCode,
		startsAt,
		expiresAt,
		businessName = null,
		status = null,
		class: className = ''
	} = $props();
</script>

<div
	class={[
		'flex flex-col items-center gap-3 rounded-card border border-line bg-surface p-4 text-center shadow-card',
		className
	].join(' ')}
>
	<div class="w-full">
		{#if businessName}<p class="font-semibold text-fg">{businessName}</p>{/if}
		<p class="text-sm text-fg-secondary">{formatDateTime(startsAt)}</p>
		{#if status}
			<div class="mt-1.5"><BookingStatusBadge {status} /></div>
		{/if}
	</div>

	<TicketQr payload={qrPayload} label={t('Check-in QR code')} class="size-52" />

	<div>
		<p class="text-xs text-fg-muted">{t('Ticket code')}</p>
		<p class="font-mono text-lg font-semibold tracking-widest text-fg" dir="ltr">{ticketCode}</p>
	</div>
	<p class="max-w-xs text-xs text-fg-muted">
		{t('Show this code at reception to check in. Valid until {when}.', {
			when: formatDateTime(expiresAt)
		})}
	</p>
	{#if status === 'draft'}
		<p class="max-w-xs text-xs text-fg-secondary">
			{t('The business will confirm your booking before your visit.')}
		</p>
	{/if}
</div>
