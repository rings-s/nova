<script>
	import Card from '../ui/Card.svelte';
	import { formatMoney } from '../../utils/money.js';
	import { formatDateTime } from '../../utils/datetime.js';
	import PaymentStatusBadge from './PaymentStatusBadge.svelte';

	/**
	 * @type {{
	 *   payment: import('../../api/payment.js').Payment,
	 *   locale?: 'en'|'ar',
	 *   actions?: import('svelte').Snippet
	 * }}
	 */
	let { payment, locale = 'en', actions } = $props();

	let refundedAmount = $derived(Number(payment.refunded_amount ?? 0));
</script>

<Card padding="sm">
	<div class="flex items-start justify-between gap-3">
		<div>
			<p class="text-lg font-semibold text-slate-900 dark:text-slate-100">
				{formatMoney(payment.amount, payment.currency, locale)}
			</p>
			<p class="text-sm text-slate-500 dark:text-slate-400">
				{payment.gateway}
				{#if payment.captured_at}
					· captured {formatDateTime(payment.captured_at, locale)}
				{/if}
			</p>
			{#if refundedAmount > 0}
				<p class="mt-1 text-sm text-amber-600">
					Refunded {formatMoney(payment.refunded_amount, payment.currency, locale)}
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
