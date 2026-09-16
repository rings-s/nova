<script>
	import Badge from '../ui/Badge.svelte';
	import { formatMoney } from '../../utils/money.js';
	import { formatDate } from '../../utils/datetime.js';

	/**
	 * @type {{
	 *   invoice: import('../../api/billing.js').Invoice,
	 *   locale?: 'en'|'ar',
	 *   onviewlines?: (invoice: import('../../api/billing.js').Invoice) => void
	 * }}
	 */
	let { invoice, locale = 'en', onviewlines } = $props();

	/** @type {Record<string, 'neutral'|'success'|'warning'|'error'|'info'|'accent'>} */
	const statusTone = {
		draft: 'neutral',
		issued: 'info',
		paid: 'success',
		overdue: 'error',
		void: 'neutral'
	};
</script>

<button
	type="button"
	onclick={() => onviewlines?.(invoice)}
	class="flex w-full items-center justify-between gap-4 rounded-lg border border-slate-200 px-4 py-3 text-start hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50"
>
	<div>
		<p class="font-medium text-slate-900 dark:text-slate-100">
			{formatDate(invoice.period_start, locale)} – {formatDate(invoice.period_end, locale)}
		</p>
		<p class="text-sm text-slate-500 dark:text-slate-400">
			{invoice.due_at ? `Due ${formatDate(invoice.due_at, locale)}` : 'Not yet issued'}
		</p>
	</div>
	<div class="flex items-center gap-3">
		<p class="text-lg font-semibold text-slate-900 dark:text-slate-100">
			{formatMoney(invoice.total_amount, invoice.currency, locale)}
		</p>
		<Badge tone={statusTone[invoice.status] ?? 'neutral'}>{invoice.status}</Badge>
	</div>
</button>
