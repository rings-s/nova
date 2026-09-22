<script>
	import Icon from '../ui/Icon.svelte';
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
	class="group duration-fast flex w-full items-center justify-between gap-4 px-5 py-3.5 text-start focus-ring transition-colors hover:bg-surface-sunken"
>
	<div class="flex min-w-0 items-center gap-3">
		<span
			class="flex size-9 shrink-0 items-center justify-center rounded-control bg-surface-muted text-fg-muted"
		>
			<Icon name="receipt" class="size-4" />
		</span>
		<div class="min-w-0">
			<p class="truncate text-sm font-medium text-fg">
				{formatDate(invoice.period_start, locale)} – {formatDate(invoice.period_end, locale)}
			</p>
			<p class="text-xs text-fg-muted">
				{invoice.due_at ? `Due ${formatDate(invoice.due_at, locale)}` : 'Not yet issued'}
			</p>
		</div>
	</div>
	<div class="flex shrink-0 items-center gap-3">
		<Badge tone={statusTone[invoice.status] ?? 'neutral'} size="sm" dot>{invoice.status}</Badge>
		<p class="w-28 text-end text-sm font-semibold text-fg tabular-nums">
			{formatMoney(invoice.total_amount, invoice.currency, locale)}
		</p>
		<Icon name="chevron-right" class="size-4 text-fg-subtle rtl:rotate-180" />
	</div>
</button>
