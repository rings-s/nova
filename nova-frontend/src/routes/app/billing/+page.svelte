<script>
	import { accessStore } from '$lib/stores/access.svelte.js';
	import NoAccess from '$lib/components/ui/NoAccess.svelte';
	/**
	 * Subscription, invoices and payouts for the active business. Subscribing,
	 * changing plan and cancelling need `manage_subscription`; everything else
	 * here needs `view_financials` — both read from this tenant's own
	 * membership row server-side, never from the client, so a lower-permission
	 * staff member simply gets a 403 with its own message if they reach this page.
	 */
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { businessStore } from '$lib/stores/business.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { formatApiError, errorMessage } from '$lib/utils/errors.js';
	import { ApiError } from '$lib/api/client.js';
	import { formatMoney } from '$lib/utils/money.js';
	import { formatDate } from '$lib/utils/datetime.js';
	import {
		listPlans,
		getSubscription,
		createSubscription,
		changePlan,
		cancelSubscription,
		listInvoices,
		listInvoiceLines,
		explainCommissionLine,
		listPayouts
	} from '$lib/api/billing.js';

	import Icon from '$lib/components/ui/Icon.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import PlanCard from '$lib/components/billing/PlanCard.svelte';
	import SubscriptionCard from '$lib/components/billing/SubscriptionCard.svelte';
	import InvoiceRow from '$lib/components/billing/InvoiceRow.svelte';

	let tenantId = $derived(/** @type {string} */ (tenantStore.activeTenantId));
	let businessId = $derived(businessStore.activeBusinessId);
	let allowed = $derived(accessStore.can('view_financials'));
	// Managers read billing; only the owner decides what the business pays NOVA.
	let canManagePlan = $derived(accessStore.can('manage_subscription'));

	let loading = $state(true);
	let loadErrorMessage = $state(/** @type {string|null} */ (null));
	let plans = $state(/** @type {import('$lib/api/billing.js').Plan[]} */ ([]));
	let subscription = $state(/** @type {import('$lib/api/billing.js').Subscription|null} */ (null));
	let subscribing = $state(false);
	let cancelling = $state(false);
	let showChangePlan = $state(false);

	let invoices = $state(/** @type {import('$lib/api/billing.js').Invoice[]} */ ([]));
	let payouts = $state(/** @type {import('$lib/api/billing.js').Payout[]} */ ([]));

	async function loadAll() {
		const currentBusinessId = businessId;
		if (!currentBusinessId) return;
		loading = true;
		loadErrorMessage = null;
		try {
			const [plansPage, invoicesPage, payoutsPage] = await Promise.all([
				listPlans(tenantId),
				listInvoices(tenantId, currentBusinessId, { limit: 20 }),
				listPayouts(tenantId, currentBusinessId, { limit: 20 })
			]);
			plans = plansPage.items;
			invoices = invoicesPage.items;
			payouts = payoutsPage.items;

			try {
				subscription = await getSubscription(tenantId, currentBusinessId);
			} catch (err) {
				if (err instanceof ApiError && err.status === 404) {
					subscription = null;
				} else {
					throw err;
				}
			}
		} catch (err) {
			loadErrorMessage = errorMessage(err);
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (businessId && allowed) loadAll();
	});

	/** @param {import('$lib/api/billing.js').Plan} plan */
	async function handleSubscribe(plan) {
		const currentBusinessId = businessId;
		if (!currentBusinessId) return;
		subscribing = true;
		try {
			subscription = await createSubscription(tenantId, {
				businessId: currentBusinessId,
				tier: plan.tier
			});
			toastStore.success(`Subscribed to ${plan.tier}.`);
		} catch (err) {
			toastStore.error(formatApiError(err));
		} finally {
			subscribing = false;
		}
	}

	/** @param {import('$lib/api/billing.js').Plan} plan */
	async function handleChangePlan(plan) {
		const currentBusinessId = businessId;
		if (!currentBusinessId) return;
		subscribing = true;
		try {
			subscription = await changePlan(tenantId, currentBusinessId, { tier: plan.tier });
			showChangePlan = false;
			toastStore.success(`Plan changed to ${plan.tier}.`);
		} catch (err) {
			toastStore.error(formatApiError(err));
		} finally {
			subscribing = false;
		}
	}

	async function handleCancel() {
		const currentBusinessId = businessId;
		if (!currentBusinessId) return;
		cancelling = true;
		try {
			subscription = await cancelSubscription(tenantId, currentBusinessId, true);
			toastStore.success('Subscription will cancel at the end of the current period.');
		} catch (err) {
			toastStore.error(formatApiError(err));
		} finally {
			cancelling = false;
		}
	}

	// --- Invoice lines --------------------------------------------------------

	let linesModalOpen = $state(false);
	let linesLoading = $state(false);
	let lines = $state(/** @type {import('$lib/api/billing.js').CommissionLine[]} */ ([]));
	let explanation = $state(/** @type {string|null} */ (null));

	/** @param {import('$lib/api/billing.js').Invoice} invoice */
	async function openLines(invoice) {
		linesModalOpen = true;
		linesLoading = true;
		explanation = null;
		try {
			const page = await listInvoiceLines(tenantId, invoice.id);
			lines = page.items;
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			linesLoading = false;
		}
	}

	/** @param {import('$lib/api/billing.js').CommissionLine} line */
	async function explainLine(line) {
		try {
			const result = await explainCommissionLine(tenantId, line.id);
			explanation = result.reason;
		} catch (err) {
			toastStore.fromError(err);
		}
	}
</script>

<svelte:head><title>Billing — NOVA</title></svelte:head>

<PageHeader
	eyebrow="Business"
	title="Billing"
	subtitle="Subscription, invoices and payouts for this business."
/>

{#snippet planActions()}
	{#if !subscription?.cancel_at_period_end}
		<Button size="sm" variant="ghost" loading={cancelling} onclick={handleCancel}>
			Cancel subscription
		</Button>
	{/if}
	<Button size="sm" variant="outline" onclick={() => (showChangePlan = true)}>Change plan</Button>
{/snippet}

{#if !allowed}
	<NoAccess what="billing" />
{:else if !businessId}
	<Alert tone="info">Set up your storefront in Catalog first.</Alert>
{:else if loading}
	<div class="flex justify-center py-12"><Spinner /></div>
{:else if loadErrorMessage}
	<Alert tone="error">{loadErrorMessage}</Alert>
{:else}
	<section class="mb-10">
		{#if subscription && !showChangePlan}
			<SubscriptionCard {subscription} actions={canManagePlan ? planActions : undefined} />
		{:else}
			{#if !subscription}
				<Alert tone="info" class="mb-4">
					{canManagePlan
						? 'Choose a plan to get started.'
						: 'This business has no plan yet. Only the owner can choose one.'}
				</Alert>
			{:else}
				<div class="mb-4 flex items-center justify-between">
					<h2 class="text-base font-semibold tracking-tight text-fg">Choose a new plan</h2>
					<Button size="sm" variant="ghost" onclick={() => (showChangePlan = false)}>Cancel</Button>
				</div>
			{/if}
			<div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
				{#each plans as plan (plan.tier)}
					<PlanCard
						{plan}
						current={subscription?.tier === plan.tier}
						onselect={canManagePlan
							? subscription
								? handleChangePlan
								: handleSubscribe
							: undefined}
					/>
				{/each}
			</div>
			{#if subscribing}
				<div class="mt-3 flex justify-center"><Spinner size="sm" /></div>
			{/if}
		{/if}
	</section>

	<section class="mb-10">
		<h2 class="mb-3 text-base font-semibold tracking-tight text-fg">Invoices</h2>
		{#if invoices.length === 0}
			<EmptyState
				title="No invoices yet"
				description="Your first invoice is issued at the end of the billing period."
			>
				{#snippet icon()}<Icon name="receipt" class="size-6" />{/snippet}
			</EmptyState>
		{:else}
			<Card padding="none" class="overflow-hidden">
				<ul class="divide-y divide-line-subtle">
					{#each invoices as invoice (invoice.id)}
						<li><InvoiceRow {invoice} onviewlines={openLines} /></li>
					{/each}
				</ul>
			</Card>
		{/if}
	</section>

	<section>
		<h2 class="mb-3 text-base font-semibold tracking-tight text-fg">Payouts</h2>
		{#if payouts.length === 0}
			<EmptyState title="No payouts yet" description="Deposits collected online are paid out here.">
				{#snippet icon()}<Icon name="credit-card" class="size-6" />{/snippet}
			</EmptyState>
		{:else}
			<Card padding="none">
				<div class="divide-y divide-line-subtle">
					{#each payouts as payout (payout.id)}
						<div class="flex items-center justify-between px-5 py-3.5">
							<div class="flex items-center gap-3">
								<span
									class="flex size-9 shrink-0 items-center justify-center rounded-control bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400"
								>
									<Icon name="trending-up" class="size-4" />
								</span>
								<div>
									<p class="text-sm font-medium text-fg">
										{formatDate(payout.payout_date, 'en')}
									</p>
									<p class="text-xs text-fg-muted">
										{payout.booking_ids.length} booking{payout.booking_ids.length === 1 ? '' : 's'}
									</p>
								</div>
							</div>
							<p class="text-sm font-semibold text-fg tabular-nums">
								{formatMoney(payout.net_amount, payout.currency, 'en')}
							</p>
						</div>
					{/each}
				</div>
			</Card>
		{/if}
	</section>
{/if}

<Modal bind:open={linesModalOpen} title="Invoice lines">
	{#if explanation}
		<Alert tone="info" class="mb-4" dismissible ondismiss={() => (explanation = null)}>
			{explanation}
		</Alert>
	{/if}
	{#if linesLoading}
		<div class="flex justify-center py-8"><Spinner /></div>
	{:else if lines.length === 0}
		<EmptyState title="No lines" />
	{:else}
		<div class="divide-y divide-line-subtle rounded-control border border-line">
			{#each lines as line (line.id)}
				<div class="flex items-center justify-between gap-3 px-4 py-3">
					<div>
						<p class="text-sm font-medium text-fg first-letter:uppercase">
							{line.commission_class.replaceAll('_', ' ')}
							{#if line.reversed}<Badge tone="warning" size="sm">reversed</Badge>{/if}
						</p>
						<button
							type="button"
							class="text-xs text-accent hover:underline"
							onclick={() => explainLine(line)}
						>
							Why?
						</button>
					</div>
					<p class="text-sm font-semibold text-fg tabular-nums">
						{formatMoney(line.amount, line.currency, 'en')}
					</p>
				</div>
			{/each}
		</div>
	{/if}
</Modal>
