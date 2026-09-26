<script>
	import { t, tp, m } from '$lib/i18n/index.svelte.js';
	/**
	 * What this business pays NOVA and what NOVA pays it: the plan (with the
	 * room it has left), the money that is due or on its way, the plans to
	 * move to, invoices and payouts.
	 *
	 * Reading needs `view_financials`; subscribing, changing plan and
	 * cancelling need `manage_subscription` (owner only). Both are checked
	 * server-side from this tenant's membership; the page only hides what the
	 * role can't use. Every plan change and a cancellation are confirmed first,
	 * with what will change spelled out, and a refusal (a downgrade the
	 * business has outgrown, 409) is shown in that same dialog.
	 */
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { accessStore } from '$lib/stores/access.svelte.js';
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { businessStore } from '$lib/stores/business.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { formatApiError, errorMessage } from '$lib/utils/errors.js';
	import { ApiError } from '$lib/api/client.js';
	import { formatMoney } from '$lib/utils/money.js';
	import {
		listPlans,
		getSubscription,
		createSubscription,
		changePlan,
		cancelSubscription,
		listInvoices,
		listPayouts,
		startPlanCheckout,
		syncPlanCheckout
	} from '$lib/api/billing.js';

	import Icon from '$lib/components/ui/Icon.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import NoAccess from '$lib/components/ui/NoAccess.svelte';
	import PlanCard from '$lib/components/billing/PlanCard.svelte';
	import CurrentPlanCard from '$lib/components/billing/CurrentPlanCard.svelte';
	import InvoiceDetail from '$lib/components/billing/InvoiceDetail.svelte';
	import {
		formatDay,
		formatPeriod,
		formatPrice,
		lastDayOf,
		planName,
		tierRank
	} from '$lib/components/billing/plans.js';

	let tenantId = $derived(/** @type {string} */ (tenantStore.activeTenantId));
	let businessId = $derived(businessStore.activeBusinessId);
	let allowed = $derived(accessStore.can('view_financials'));
	// Managers read billing; only the owner decides what the business pays NOVA.
	let canManagePlan = $derived(accessStore.can('manage_subscription'));

	let loading = $state(true);
	let loadErrorMessage = $state(/** @type {string|null} */ (null));
	let plans = $state(/** @type {import('$lib/api/billing.js').Plan[]} */ ([]));
	let subscription = $state(/** @type {import('$lib/api/billing.js').Subscription|null} */ (null));
	let invoices = $state(/** @type {import('$lib/api/billing.js').Invoice[]} */ ([]));
	let payouts = $state(/** @type {import('$lib/api/billing.js').Payout[]} */ ([]));

	$effect(() => {
		const business = businessId;
		const tenant = tenantId;
		if (!business || !allowed) return;
		let cancelled = false;
		loading = true;
		loadErrorMessage = null;
		Promise.all([
			listPlans(tenant),
			listInvoices(tenant, business, { limit: 24 }),
			listPayouts(tenant, business, { limit: 24 }),
			getSubscription(tenant, business).catch((err) => {
				// No subscription yet is a state, not a failure.
				if (err instanceof ApiError && err.status === 404) return null;
				throw err;
			})
		])
			.then(([plansPage, invoicesPage, payoutsPage, current]) => {
				if (cancelled) return;
				plans = [...plansPage.items].sort((a, b) => tierRank(a.tier) - tierRank(b.tier));
				invoices = invoicesPage.items;
				payouts = payoutsPage.items;
				subscription = current;
				annual = current?.annual ?? false;
			})
			.catch((err) => {
				if (!cancelled) loadErrorMessage = errorMessage(err);
			})
			.finally(() => {
				if (!cancelled) loading = false;
			});
		return () => {
			cancelled = true;
		};
	});

	let currentPlan = $derived(plans.find((p) => p.tier === subscription?.tier) ?? null);
	let anyAnnual = $derived(plans.some((p) => p.annual_price !== null));
	let annual = $state(false);

	// --- Money due and money coming ------------------------------------------------

	let unpaid = $derived(invoices.filter((i) => i.status === 'issued' || i.status === 'overdue'));
	let overdue = $derived(invoices.filter((i) => i.status === 'overdue'));
	let amountDue = $derived(unpaid.reduce((sum, i) => sum + Number(i.total_amount), 0));
	let nextDue = $derived(
		unpaid
			.map((i) => i.due_at)
			.filter(Boolean)
			.sort()[0] ?? null
	);
	let latestPayout = $derived(
		[...payouts].sort((a, b) => b.payout_date.localeCompare(a.payout_date))[0] ?? null
	);
	let pendingPayouts = $derived(payouts.filter((p) => !p.paid_at));
	let currency = $derived(subscription?.currency ?? plans[0]?.currency ?? 'SAR');

	// --- Changing plan ---------------------------------------------------------------

	let target = $state(/** @type {import('$lib/api/billing.js').Plan|null} */ (null));
	let targetAnnual = $state(false);
	let changing = $state(false);
	let changeError = $state(/** @type {string|null} */ (null));

	/** @param {import('$lib/api/billing.js').Plan} plan */
	function askToChange(plan) {
		target = plan;
		targetAnnual = annual && plan.annual_price !== null;
		changeError = null;
	}

	async function confirmChange() {
		const plan = target;
		const business = businessId;
		if (!plan || !business) return;
		changing = true;
		changeError = null;
		try {
			subscription = subscription
				? await changePlan(tenantId, business, { tier: plan.tier, annual: targetAnnual })
				: await createSubscription(tenantId, {
						businessId: business,
						tier: plan.tier,
						annual: targetAnnual
					});
			target = null;
			if (subscription.status === 'pending_payment') {
				// A paid plan starts once it is paid for: straight to Moyasar.
				await payNow();
			} else {
				toastStore.success(t("You're on {plan} now.", { plan: planName(plan.tier) }));
			}
		} catch (err) {
			// A refusal (e.g. more branches than the plan allows) belongs in the dialog.
			changeError = formatApiError(err);
		} finally {
			changing = false;
		}
	}

	// Moving onto a paid plan from nothing, Solo, or an unpaid choice is paid
	// for on Moyasar before it applies (the server decides; this only words it).
	let needsPayment = $derived(
		!!target &&
			Number(target.monthly_price) > 0 &&
			(!subscription ||
				subscription.status === 'pending_payment' ||
				Number(currentPlan?.monthly_price ?? 0) === 0)
	);

	let isUpgrade = $derived(
		!!target && !!subscription && tierRank(target.tier) > tierRank(subscription.tier)
	);

	// --- Paying for a plan -------------------------------------------------------------

	let paying = $state(false);

	/**
	 * Opens Moyasar's payment page for the plan waiting on payment. Moyasar sends
	 * the owner back here with `?checkout=<id>`, handled below.
	 */
	async function payNow() {
		const business = businessId;
		if (!business) return;
		paying = true;
		try {
			const checkout = await startPlanCheckout(
				tenantId,
				business,
				new URL(resolve('/app/billing'), window.location.origin).href
			);
			if (!checkout.redirect_url?.startsWith('https://')) {
				throw new Error(t('The payment page could not be opened. Try again.'));
			}
			window.location.assign(checkout.redirect_url);
		} catch (err) {
			toastStore.error(formatApiError(err));
			paying = false;
		}
	}

	// Back from Moyasar: ask the API how it went (the redirect alone proves
	// nothing), then drop `?checkout=` so a reload does not ask again.
	let returnedCheckout = $derived(page.url.searchParams.get('checkout'));
	$effect(() => {
		const checkoutId = returnedCheckout;
		const business = businessId;
		const tenant = tenantId;
		if (!checkoutId || !business || !tenant) return;
		syncPlanCheckout(tenant, checkoutId)
			.then(async (checkout) => {
				if (checkout.status === 'paid') {
					toastStore.success(
						t('Payment received. You are on {plan} now.', { plan: planName(checkout.tier) })
					);
				} else if (checkout.status === 'failed') {
					toastStore.error(t('The payment did not go through. Nothing was charged.'));
				} else {
					toastStore.info(t('Your payment is still being confirmed. Check back in a minute.'));
				}
				subscription = await getSubscription(tenant, business);
			})
			.catch((err) => toastStore.fromError(err))
			.finally(() => goto(resolve('/app/billing'), { replaceState: true, noScroll: true }));
	});

	// --- Cancelling -----------------------------------------------------------------

	let confirmingCancel = $state(false);
	let cancelling = $state(false);

	async function confirmCancel() {
		const business = businessId;
		if (!business) return;
		cancelling = true;
		try {
			subscription = await cancelSubscription(tenantId, business, true);
			confirmingCancel = false;
			toastStore.success(t('Your plan will end with this billing period.'));
		} catch (err) {
			toastStore.error(formatApiError(err));
		} finally {
			cancelling = false;
		}
	}

	// --- Invoices -------------------------------------------------------------------

	let openInvoice = $state(/** @type {import('$lib/api/billing.js').Invoice|null} */ (null));
	let invoiceOpen = $derived(openInvoice !== null);

	/** @type {Record<string, { label: string, tone: 'neutral'|'success'|'warning'|'error'|'info' }>} */
	const INVOICE_STATUS = {
		draft: { label: m('Draft'), tone: 'neutral' },
		issued: { label: m('Due'), tone: 'info' },
		paid: { label: m('Paid'), tone: 'success' },
		overdue: { label: m('Overdue'), tone: 'error' },
		void: { label: m('Void'), tone: 'neutral' }
	};

	/** @param {string|number} amount */
	const money = (amount) => formatMoney(amount, currency);
</script>

<svelte:head><title>{t('Billing')} — NOVA</title></svelte:head>

<PageHeader
	eyebrow={t('Business')}
	title={t('Billing')}
	subtitle={t('Your plan, what you owe NOVA, and what NOVA pays out to you.')}
/>

{#snippet planActions()}
	{#if canManagePlan}
		{#if !subscription?.cancel_at_period_end && subscription?.status !== 'cancelled'}
			<Button size="sm" variant="danger-ghost" onclick={() => (confirmingCancel = true)}>
				{t('Cancel plan')}
			</Button>
		{/if}
		<Button size="sm" variant="outline" href="#plans">
			{t('Compare plans')}
			<Icon name="arrow-right" class="size-3.5 rtl:rotate-180" />
		</Button>
	{:else}
		<p class="me-auto text-xs text-fg-muted">{t('Only the business owner can change the plan.')}</p>
	{/if}
{/snippet}

{#if !allowed}
	<NoAccess what={t('billing')} />
{:else if !businessId}
	<Alert tone="info">{t('Set up your storefront in Catalog first.')}</Alert>
{:else if loading}
	<div class="grid gap-4 lg:grid-cols-[1.7fr_1fr]">
		<Skeleton class="h-80 rounded-panel" />
		<div class="flex flex-col gap-4">
			<Skeleton class="h-38 rounded-card" />
			<Skeleton class="h-38 rounded-card" />
		</div>
	</div>
{:else if loadErrorMessage}
	<Alert tone="error">{loadErrorMessage}</Alert>
{:else}
	<!-- What needs attention first -->
	{#if subscription?.marketplace_listing_hidden}
		<Alert tone="error" class="mb-4">
			{t(
				'Your marketplace listing is hidden until the overdue invoice is paid. Your calendar, queue and existing bookings keep working.'
			)}
		</Alert>
	{:else if overdue.length}
		<Alert tone="warning" class="mb-4">
			{overdue.length === 1
				? t('The {period} invoice is overdue.', {
						period: formatPeriod(overdue[0].period_start, overdue[0].period_end)
					})
				: tp(overdue.length, '{count} invoice is overdue.', '{count} invoices are overdue.')}
			{t('After 21 days overdue, your marketplace listing is hidden until it is paid.')}
		</Alert>
	{/if}
	{#if subscription?.status === 'pending_payment'}
		<Alert tone="warning" class="mb-4">
			<div class="flex flex-wrap items-center justify-between gap-3">
				<span>
					{t('{plan} starts once it is paid for. Until then your business is on Solo terms.', {
						plan: planName(subscription.tier)
					})}
				</span>
				{#if canManagePlan}
					<Button size="sm" loading={paying} onclick={payNow}>{t('Pay now')}</Button>
				{/if}
			</div>
		</Alert>
	{/if}
	{#if subscription?.cancel_at_period_end && subscription.status !== 'cancelled'}
		<Alert tone="warning" class="mb-4">
			{t('{plan} ends on {date}. To keep it, contact NOVA support before then.', {
				plan: planName(subscription.tier),
				date: formatDay(lastDayOf(subscription.current_period_end))
			})}
		</Alert>
	{/if}

	<!-- Plan and money -->
	<div class="grid gap-4 lg:grid-cols-[1.7fr_1fr]">
		{#if subscription}
			<CurrentPlanCard {subscription} plan={currentPlan} actions={planActions} />
		{:else}
			<section
				class="flex flex-col justify-center gap-4 rounded-panel border border-dashed border-line-strong bg-surface p-8"
			>
				<span
					class="flex size-11 items-center justify-center rounded-card bg-accent-soft text-accent"
				>
					<Icon name="sparkles" class="size-5" />
				</span>
				<div>
					<h2 class="text-xl font-semibold tracking-tight text-fg">{t('No plan yet')}</h2>
					<p class="mt-1 max-w-md text-sm text-fg-muted">
						{canManagePlan
							? t(
									'Your business is on Solo terms until you choose a plan. Solo is free: NOVA takes commission only on new clients it brings you.'
								)
							: t('Your business is on Solo terms. Only the owner can choose a plan.')}
					</p>
				</div>
				{#if canManagePlan}
					<div><Button href="#plans">{t('Choose a plan')}</Button></div>
				{/if}
			</section>
		{/if}

		<div class="flex flex-col gap-4">
			<section
				class="flex flex-1 flex-col rounded-card border border-line bg-surface p-5 shadow-card"
				aria-labelledby="due-heading"
			>
				<div class="flex items-center justify-between">
					<h2 id="due-heading" class="text-sm font-medium text-fg-muted">{t('Due to NOVA')}</h2>
					<Icon name="receipt" class="size-4 text-fg-subtle" />
				</div>
				<p class="mt-2 text-3xl font-semibold tracking-tight text-fg">{money(amountDue)}</p>
				<p class="mt-1 text-sm text-fg-muted">
					{#if !unpaid.length}
						{t("Nothing to pay. You're up to date.")}
					{:else}
						{tp(unpaid.length, '{count} invoice', '{count} invoices')}{nextDue
							? ` · ${t('next due {date}', { date: formatDay(nextDue) })}`
							: ''}
					{/if}
				</p>
			</section>
			<section
				class="flex flex-1 flex-col rounded-card border border-line bg-surface p-5 shadow-card"
				aria-labelledby="payout-heading"
			>
				<div class="flex items-center justify-between">
					<h2 id="payout-heading" class="text-sm font-medium text-fg-muted">
						{t('Latest payout')}
					</h2>
					<Icon name="trending-up" class="size-4 text-fg-subtle" />
				</div>
				{#if latestPayout}
					<p class="mt-2 text-3xl font-semibold tracking-tight text-fg">
						{formatMoney(latestPayout.net_amount, latestPayout.currency)}
					</p>
					<p class="mt-1 text-sm text-fg-muted">
						{latestPayout.paid_at
							? t('Paid {date}', { date: formatDay(latestPayout.paid_at) })
							: t('Scheduled {date}', { date: formatDay(latestPayout.payout_date) })}
						{#if pendingPayouts.length}
							· {t('{count} on the way', { count: pendingPayouts.length })}
						{/if}
					</p>
				{:else}
					<p class="mt-2 text-3xl font-semibold tracking-tight text-fg-subtle">—</p>
					<p class="mt-1 text-sm text-fg-muted">
						{t('Deposits customers pay online arrive here.')}
					</p>
				{/if}
			</section>
		</div>
	</div>

	<!-- Plans -->
	<section id="plans" class="mt-14 scroll-mt-20" aria-labelledby="plans-heading">
		<div class="mb-6 flex flex-wrap items-end justify-between gap-4">
			<div>
				<h2 id="plans-heading" class="text-lg font-semibold tracking-tight text-fg">
					{t('Plans')}
				</h2>
				<p class="text-sm text-fg-muted">
					{t("Change any time. Commission you've already earned keeps the rate it was earned at.")}
				</p>
			</div>
			{#if anyAnnual}
				<div
					class="inline-flex gap-1 rounded-control bg-surface-muted p-1"
					role="radiogroup"
					aria-label={t('Billing cycle')}
				>
					{#each [{ value: false, label: t('Monthly') }, { value: true, label: t('Yearly') }] as cycle (cycle.value)}
						<button
							type="button"
							role="radio"
							aria-checked={annual === cycle.value}
							onclick={() => (annual = cycle.value)}
							class={[
								'inline-flex h-8 items-center gap-1.5 rounded-[calc(var(--radius-control)-2px)] px-3.5 text-sm font-medium focus-ring transition-[background-color,color,box-shadow] duration-fast',
								annual === cycle.value
									? 'bg-surface text-fg shadow-card ring-1 ring-line dark:bg-slate-700/60 dark:ring-white/5'
									: 'text-fg-muted hover:text-fg'
							].join(' ')}
						>
							{cycle.label}
							{#if cycle.value}
								<span
									class="rounded-full bg-emerald-50 px-1.5 text-[11px] font-semibold text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
									>{t('Save')}</span
								>
							{/if}
						</button>
					{/each}
				</div>
			{/if}
		</div>
		<div class="grid gap-4 lg:grid-cols-3">
			{#each plans as plan, i (plan.tier)}
				<PlanCard
					{plan}
					below={i > 0 ? plans[i - 1] : null}
					{annual}
					{subscription}
					onselect={canManagePlan ? askToChange : null}
				/>
			{/each}
		</div>
	</section>

	<!-- Invoices -->
	<section class="mt-14" aria-labelledby="invoices-heading">
		<div class="mb-4">
			<h2 id="invoices-heading" class="text-lg font-semibold tracking-tight text-fg">
				{t('Invoices')}
			</h2>
			<p class="text-sm text-fg-muted">
				{t('One a month: your plan, commission on new marketplace clients, processing and VAT.')}
			</p>
		</div>
		{#if invoices.length === 0}
			<div
				class="flex flex-col items-center gap-2 rounded-card border border-line bg-surface p-10 text-center shadow-card"
			>
				<Icon name="receipt" class="size-5 text-fg-subtle" />
				<p class="text-sm font-medium text-fg">{t('No invoices yet')}</p>
				<p class="text-sm text-fg-muted">{t('The first one is issued when this month closes.')}</p>
			</div>
		{:else}
			<ul
				class="divide-y divide-line-subtle overflow-hidden rounded-card border border-line bg-surface shadow-card sm:hidden"
			>
				{#each invoices as invoice (invoice.id)}
					{@const status = INVOICE_STATUS[invoice.status] ?? {
						label: invoice.status,
						tone: 'neutral'
					}}
					<li>
						<button
							type="button"
							class="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-start focus-ring"
							onclick={() => (openInvoice = invoice)}
						>
							<span class="min-w-0">
								<span class="block text-sm font-medium text-fg">
									{formatPeriod(invoice.period_start, invoice.period_end)}
								</span>
								<span class="mt-1 flex items-center gap-2 text-xs text-fg-muted">
									<Badge tone={status.tone} size="sm" dot>{t(status.label)}</Badge>
									{invoice.status === 'paid'
										? formatDay(invoice.paid_at, { year: false })
										: t('due {date}', { date: formatDay(invoice.due_at, { year: false }) })}
								</span>
							</span>
							<span class="flex shrink-0 items-center gap-2">
								<span class="text-sm font-semibold text-fg tabular-nums">
									{formatMoney(invoice.total_amount, invoice.currency)}
								</span>
								<Icon name="chevron-right" class="size-4 text-fg-subtle rtl:rotate-180" />
							</span>
						</button>
					</li>
				{/each}
			</ul>
			<div
				class="hidden overflow-x-auto rounded-card border border-line bg-surface shadow-card sm:block"
			>
				<table class="w-full min-w-[560px] text-sm">
					<thead>
						<tr class="border-b border-line bg-surface-sunken text-xs text-fg-muted">
							<th scope="col" class="px-5 py-2.5 text-start font-medium">{t('Period')}</th>
							<th scope="col" class="px-4 py-2.5 text-start font-medium">{t('Status')}</th>
							<th scope="col" class="px-4 py-2.5 text-start font-medium">{t('Due')}</th>
							<th scope="col" class="px-4 py-2.5 text-end font-medium">{t('Total')}</th>
							<th scope="col" class="w-12 px-4 py-2.5"><span class="sr-only">{t('Open')}</span></th>
						</tr>
					</thead>
					<tbody class="divide-y divide-line-subtle">
						{#each invoices as invoice (invoice.id)}
							{@const status = INVOICE_STATUS[invoice.status] ?? {
								label: invoice.status,
								tone: 'neutral'
							}}
							<tr
								class="group cursor-pointer transition-colors hover:bg-surface-sunken"
								onclick={() => (openInvoice = invoice)}
							>
								<th scope="row" class="px-5 py-3.5 text-start font-medium text-fg">
									<button
										type="button"
										class="rounded text-start focus-ring"
										onclick={(event) => {
											event.stopPropagation();
											openInvoice = invoice;
										}}
									>
										{formatPeriod(invoice.period_start, invoice.period_end)}
									</button>
								</th>
								<td class="px-4 py-3.5">
									<Badge tone={status.tone} size="sm" dot>{t(status.label)}</Badge>
								</td>
								<td class="px-4 py-3.5 text-fg-secondary">
									{invoice.status === 'paid'
										? t('Paid {date}', { date: formatDay(invoice.paid_at) })
										: formatDay(invoice.due_at)}
								</td>
								<td class="px-4 py-3.5 text-end font-semibold text-fg tabular-nums">
									{formatMoney(invoice.total_amount, invoice.currency)}
								</td>
								<td class="px-4 py-3.5 text-end">
									<Icon
										name="chevron-right"
										class="size-4 text-fg-subtle transition-transform group-hover:translate-x-0.5 rtl:rotate-180"
									/>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</section>

	<!-- Payouts -->
	<section class="mt-14" aria-labelledby="payouts-heading">
		<div class="mb-4">
			<h2 id="payouts-heading" class="text-lg font-semibold tracking-tight text-fg">
				{t('Payouts')}
			</h2>
			<p class="text-sm text-fg-muted">
				{t(
					'What customers paid online, less processing and any commission netted, sent to your account.'
				)}
			</p>
		</div>
		{#if payouts.length === 0}
			<div
				class="flex flex-col items-center gap-2 rounded-card border border-line bg-surface p-10 text-center shadow-card"
			>
				<Icon name="credit-card" class="size-5 text-fg-subtle" />
				<p class="text-sm font-medium text-fg">{t('No payouts yet')}</p>
				<p class="text-sm text-fg-muted">
					{t('When customers pay deposits online, the money is paid out here.')}
				</p>
			</div>
		{:else}
			<ul
				class="divide-y divide-line-subtle overflow-hidden rounded-card border border-line bg-surface shadow-card sm:hidden"
			>
				{#each payouts as payout (payout.id)}
					<li class="flex items-center justify-between gap-3 px-4 py-3.5">
						<span class="min-w-0">
							<span class="block text-sm font-medium text-fg">{formatDay(payout.payout_date)}</span>
							<span class="mt-0.5 block text-xs text-fg-muted">
								{tp(payout.booking_ids.length, '{count} booking', '{count} bookings')} ·
								{t('{amount} collected', {
									amount: formatMoney(payout.collected_amount, payout.currency)
								})}
							</span>
						</span>
						<span class="flex shrink-0 flex-col items-end gap-1">
							<span class="text-sm font-semibold text-fg tabular-nums">
								{formatMoney(payout.net_amount, payout.currency)}
							</span>
							{#if payout.paid_at}
								<Badge tone="success" size="sm" dot>{t('Paid')}</Badge>
							{:else}
								<Badge tone="info" size="sm" dot>{t('On the way')}</Badge>
							{/if}
						</span>
					</li>
				{/each}
			</ul>
			<div
				class="hidden overflow-x-auto rounded-card border border-line bg-surface shadow-card sm:block"
			>
				<table class="w-full min-w-[680px] text-sm">
					<thead>
						<tr class="border-b border-line bg-surface-sunken text-xs text-fg-muted">
							<th scope="col" class="px-5 py-2.5 text-start font-medium">{t('Date')}</th>
							<th scope="col" class="px-4 py-2.5 text-end font-medium">{t('Bookings')}</th>
							<th scope="col" class="px-4 py-2.5 text-end font-medium">{t('Collected')}</th>
							<th scope="col" class="px-4 py-2.5 text-end font-medium">{t('Processing')}</th>
							<th scope="col" class="px-4 py-2.5 text-end font-medium">{t('Commission')}</th>
							<th scope="col" class="px-4 py-2.5 text-end font-medium">{t('You receive')}</th>
							<th scope="col" class="px-5 py-2.5 text-start font-medium">{t('Status')}</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-line-subtle">
						{#each payouts as payout (payout.id)}
							<tr class="transition-colors hover:bg-surface-sunken">
								<th
									scope="row"
									class="px-5 py-3.5 text-start font-medium whitespace-nowrap text-fg"
								>
									{formatDay(payout.payout_date)}
								</th>
								<td class="px-4 py-3.5 text-end text-fg-secondary tabular-nums">
									{payout.booking_ids.length}
								</td>
								<td class="px-4 py-3.5 text-end whitespace-nowrap text-fg-secondary tabular-nums">
									{formatMoney(payout.collected_amount, payout.currency)}
								</td>
								<td class="px-4 py-3.5 text-end whitespace-nowrap text-fg-muted tabular-nums">
									{Number(payout.processing_fee)
										? `− ${formatMoney(payout.processing_fee, payout.currency)}`
										: '—'}
								</td>
								<td class="px-4 py-3.5 text-end whitespace-nowrap text-fg-muted tabular-nums">
									{Number(payout.commission_netted)
										? `− ${formatMoney(payout.commission_netted, payout.currency)}`
										: '—'}
								</td>
								<td class="px-4 py-3.5 text-end font-semibold text-fg tabular-nums">
									{formatMoney(payout.net_amount, payout.currency)}
								</td>
								<td class="px-5 py-3.5">
									{#if payout.paid_at}
										<Badge tone="success" size="sm" dot
											>{t('Paid {date}', {
												date: formatDay(payout.paid_at, { year: false })
											})}</Badge
										>
									{:else}
										<Badge tone="info" size="sm" dot>{t('On the way')}</Badge>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</section>
{/if}

<!-- Invoice -->
<Modal
	open={invoiceOpen}
	onclose={() => (openInvoice = null)}
	size="lg"
	title={openInvoice
		? t('Invoice · {period}', {
				period: formatPeriod(openInvoice.period_start, openInvoice.period_end)
			})
		: ''}
>
	{#if openInvoice}
		<InvoiceDetail {tenantId} invoice={openInvoice} />
	{/if}
</Modal>

<!-- Change plan -->
<Modal
	open={target !== null}
	onclose={() => (target = null)}
	title={target
		? subscription
			? isUpgrade
				? t('Upgrade to {plan}?', { plan: planName(target.tier) })
				: t('Move to {plan}?', { plan: planName(target.tier) })
			: t('Start on {plan}?', { plan: planName(target.tier) })
		: ''}
>
	{#if target}
		{@const price = targetAnnual ? target.annual_price : target.monthly_price}
		<div class="flex flex-col gap-4">
			{#if changeError}
				<Alert tone="error">{changeError}</Alert>
			{/if}
			<dl class="divide-y divide-line-subtle rounded-control border border-line text-sm">
				<div class="flex items-center justify-between gap-3 px-4 py-3">
					<dt class="text-fg-muted">{t('Price')}</dt>
					<dd class="font-medium text-fg">
						{#if Number(target.monthly_price) === 0}
							{t('Free')}
						{:else}
							{formatPrice(price ?? target.monthly_price, target.currency)} / {targetAnnual
								? t('year')
								: t('month')}{target.priced_per_location ? ` ${t('per branch')}` : ''}
							{#if target.priced_per_location && (subscription?.locations ?? 1) > 1}
								<span class="block text-xs font-normal text-fg-muted">
									{t('{amount} a month for your {count} branches', {
										amount: formatPrice(
											Number(target.monthly_price) * (subscription?.locations ?? 1),
											target.currency
										),
										count: subscription?.locations
									})}
								</span>
							{/if}
						{/if}
					</dd>
				</div>
				<div class="flex items-center justify-between gap-3 px-4 py-3">
					<dt class="text-fg-muted">{t('Commission on new marketplace clients')}</dt>
					<dd class="font-medium text-fg">
						{#if currentPlan && currentPlan.tier !== target.tier}
							<span class="text-fg-subtle line-through"
								>{Number(currentPlan.new_client_commission_pct)}%</span
							>
						{/if}
						{Number(target.new_client_commission_pct)}%
					</dd>
				</div>
				{#if target.contract_months}
					<div class="flex items-center justify-between gap-3 px-4 py-3">
						<dt class="text-fg-muted">{t('Commitment')}</dt>
						<dd class="font-medium text-fg">
							{t('{count} months', { count: target.contract_months })}
						</dd>
					</div>
				{/if}
			</dl>
			{#if target.annual_price !== null}
				<label class="flex items-center gap-2.5 text-sm text-fg-secondary">
					<input type="checkbox" class="size-4 accent-brand-600" bind:checked={targetAnnual} />
					{t('Pay yearly ({amount} a year)', {
						amount: formatPrice(target.annual_price, target.currency)
					})}
				</label>
			{/if}
			<p class="text-sm text-fg-muted">
				{#if needsPayment}
					{t(
						"Next, you pay on Moyasar's secure page (price plus 15% VAT). The plan starts as soon as the payment is confirmed."
					)}
				{:else}
					{t(
						'The change takes effect straight away. Commission on bookings already completed keeps the rate it was earned at.'
					)}
				{/if}
			</p>
		</div>
	{/if}
	{#snippet footer()}
		<Button variant="ghost" onclick={() => (target = null)}>{t('Not now')}</Button>
		<Button loading={changing} onclick={confirmChange}>
			{needsPayment
				? t('Continue to payment')
				: subscription
					? t('Confirm change')
					: t('Start plan')}
		</Button>
	{/snippet}
</Modal>

<!-- Cancel -->
<Modal
	open={confirmingCancel}
	onclose={() => (confirmingCancel = false)}
	title={t('Cancel your plan?')}
	size="sm"
>
	{#if subscription}
		<p class="text-sm text-fg-secondary">
			{t(
				"{plan} stays active until {date}, the end of the period you've paid for. After that, its paid features stop. To change your mind later, you'll need to contact NOVA support.",
				{
					plan: planName(subscription.tier),
					date: formatDay(lastDayOf(subscription.current_period_end))
				}
			)}
		</p>
	{/if}
	{#snippet footer()}
		<Button variant="ghost" onclick={() => (confirmingCancel = false)}>{t('Keep my plan')}</Button>
		<Button variant="danger" loading={cancelling} onclick={confirmCancel}>{t('Cancel plan')}</Button
		>
	{/snippet}
</Modal>
