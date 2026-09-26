<script>
	import { t, m } from '$lib/i18n/index.svelte.js';
	/**
	 * One invoice, opened: what it charges for (subscription, commission,
	 * processing, VAT) as a part-to-whole bar with the figures beside it, and
	 * the commission lines behind the commission figure. Each line can say
	 * why it was billed at its rate (`/commission-lines/{id}/explain`),
	 * fetched only when asked.
	 */
	import { explainCommissionLine, listInvoiceLines } from '../../api/billing.js';
	import { toastStore } from '../../stores/toast.svelte.js';
	import { formatMoney } from '../../utils/money.js';
	import Badge from '../ui/Badge.svelte';
	import Skeleton from '../ui/Skeleton.svelte';
	import Icon from '../ui/Icon.svelte';
	import PartsBar from '../analytics/viz/PartsBar.svelte';
	import { formatDay } from './plans.js';

	/**
	 * @type {{
	 *   tenantId: string,
	 *   invoice: import('../../api/billing.js').Invoice
	 * }}
	 */
	let { tenantId, invoice } = $props();

	const CLASS_LABELS = {
		new_marketplace: m('New client from the marketplace'),
		repeat: m('Returning client'),
		direct: m('Your own client'),
		exempt: m('Not billable')
	};
	/** @param {string} value */
	const classLabel = (value) =>
		t(/** @type {Record<string, string>} */ (CLASS_LABELS)[value] ?? value.replaceAll('_', ' '));

	let lines = $state(/** @type {import('../../api/billing.js').CommissionLine[]|null} */ (null));
	/** @type {Record<string, string|'loading'>} */
	let reasons = $state({});

	$effect(() => {
		const id = invoice.id;
		let cancelled = false;
		lines = null;
		listInvoiceLines(tenantId, id)
			.then((page) => {
				if (!cancelled) lines = page.items;
			})
			.catch((err) => {
				if (!cancelled) {
					lines = [];
					toastStore.fromError(err);
				}
			});
		return () => {
			cancelled = true;
		};
	});

	/** @param {import('../../api/billing.js').CommissionLine} line */
	async function toggleReason(line) {
		if (reasons[line.id] && reasons[line.id] !== 'loading') {
			delete reasons[line.id];
			return;
		}
		reasons[line.id] = 'loading';
		try {
			reasons[line.id] = (await explainCommissionLine(tenantId, line.id)).reason;
		} catch (err) {
			delete reasons[line.id];
			toastStore.fromError(err);
		}
	}

	let charges = $derived(
		/** @type {import('../../utils/chartData.js').PartsModel} */ ({
			type: 'parts',
			unit: 'money',
			parts: [
				{
					label: t('Subscription'),
					value: Number(invoice.subscription_amount),
					color: 'var(--chart-series-1)'
				},
				{
					label: t('Commission'),
					value: Number(invoice.commission_amount),
					color: 'var(--chart-series-2)'
				},
				{
					label: t('Payment processing'),
					value: Number(invoice.processing_amount),
					color: 'var(--chart-series-3)'
				},
				{ label: t('VAT'), value: Number(invoice.vat_amount), color: 'var(--chart-series-4)' }
			]
		})
	);
	let hasCharges = $derived(charges.parts.some((part) => part.value > 0));
</script>

<div class="flex flex-col gap-6">
	<div class="flex flex-wrap items-end justify-between gap-3">
		<div>
			<p class="text-xs text-fg-muted">{t('Total')}</p>
			<p class="text-3xl font-semibold tracking-tight text-fg">
				{formatMoney(invoice.total_amount, invoice.currency)}
			</p>
		</div>
		<dl class="flex gap-6 text-sm">
			<div>
				<dt class="text-xs text-fg-muted">{t('Issued')}</dt>
				<dd class="font-medium text-fg">{formatDay(invoice.issued_at)}</dd>
			</div>
			<div>
				<dt class="text-xs text-fg-muted">{invoice.paid_at ? t('Paid') : t('Due')}</dt>
				<dd class="font-medium text-fg">{formatDay(invoice.paid_at ?? invoice.due_at)}</dd>
			</div>
		</dl>
	</div>

	{#if hasCharges}
		<PartsBar model={charges} currency={invoice.currency} />
	{/if}

	<div>
		<h3 class="mb-2 text-sm font-semibold text-fg">{t('Commission lines')}</h3>
		{#if lines === null}
			<div class="flex flex-col gap-2">
				<Skeleton class="h-12 rounded-control" />
				<Skeleton class="h-12 rounded-control" />
			</div>
		{:else if lines.length === 0}
			<p class="rounded-control bg-surface-sunken px-4 py-3 text-sm text-fg-muted">
				{t('No commission on this invoice.')}
			</p>
		{:else}
			<ul
				class="max-h-80 divide-y divide-line-subtle overflow-y-auto rounded-control border border-line"
			>
				{#each lines as line (line.id)}
					{@const reason = reasons[line.id]}
					<li class="px-4 py-3">
						<div class="flex items-start justify-between gap-3">
							<div class="min-w-0">
								<p class="flex flex-wrap items-center gap-2 text-sm font-medium text-fg">
									{classLabel(line.commission_class)}
									{#if line.reversed || line.is_reversal}
										<Badge tone="warning" size="sm"
											>{line.is_reversal ? t('Reversal') : t('Reversed')}</Badge
										>
									{/if}
								</p>
								<p class="mt-0.5 text-xs text-fg-muted">
									{t('{percent}% of {amount}', {
										percent: Number(line.rate_pct),
										amount: formatMoney(line.base_amount, line.currency)
									})} · {formatDay(line.accrued_at)}
								</p>
							</div>
							<div class="flex shrink-0 flex-col items-end gap-1">
								<p class="text-sm font-semibold text-fg tabular-nums">
									{formatMoney(line.amount, line.currency)}
								</p>
								<button
									type="button"
									class="inline-flex items-center gap-1 rounded text-xs font-medium text-accent focus-ring hover:underline"
									aria-expanded={!!reason && reason !== 'loading'}
									onclick={() => toggleReason(line)}
								>
									<Icon name="info" class="size-3.5" />
									{reason && reason !== 'loading' ? t('Hide') : t('Why this rate?')}
								</button>
							</div>
						</div>
						{#if reason === 'loading'}
							<Skeleton class="mt-2 h-8 rounded-control" />
						{:else if reason}
							<p
								class="mt-2 animate-fade-in rounded-control bg-surface-sunken px-3 py-2 text-xs text-fg-secondary"
							>
								{reason}
							</p>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>
