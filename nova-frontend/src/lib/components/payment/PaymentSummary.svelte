<script>
	import { t } from '$lib/i18n/index.svelte.js';
	import Card from '../ui/Card.svelte';
	import { formatMoney } from '../../utils/money.js';
	import { formatDateTime } from '../../utils/datetime.js';
	import PaymentStatusBadge from './PaymentStatusBadge.svelte';

	/**
	 * @type {{
	 *   payment: import('../../api/payment.js').Payment,
	 *   actions?: import('svelte').Snippet
	 * }}
	 */
	let { payment, actions } = $props();

	let refundedAmount = $derived(Number(payment.refunded_amount ?? 0));
</script>

<Card padding="sm">
	<div class="flex items-start justify-between gap-3">
		<div>
			<p class="text-lg font-semibold text-fg">
				{formatMoney(payment.amount, payment.currency)}
			</p>
			<p class="text-sm text-fg-muted">
				{payment.gateway}
				{#if payment.captured_at}
					· {t('paid {time}', { time: formatDateTime(payment.captured_at) })}
				{/if}
			</p>
			{#if refundedAmount > 0}
				<p class="mt-1 text-sm text-amber-600">
					{t('Refunded {amount}', {
						amount: formatMoney(payment.refunded_amount, payment.currency)
					})}
				</p>
			{/if}
			{#if payment.failure_code}
				<p class="mt-1 text-sm text-red-600">{payment.failure_code}</p>
			{/if}
		</div>
		<PaymentStatusBadge status={payment.status} />
	</div>
	{#if actions}
		<div class="mt-3 flex gap-2">{@render actions()}</div>
	{/if}
</Card>
