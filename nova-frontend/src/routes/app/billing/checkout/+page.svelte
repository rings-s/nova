<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * Paying for a plan, in NOVA's own page: what is being bought on one side,
	 * Moyasar's card form (themed to match, `MoyasarForm`) on the other.
	 *
	 * Opening the page opens the checkout (`startPlanCheckout`), so a reload
	 * opens a fresh invoice rather than paying a stale one. Moyasar sends the
	 * owner back to `/app/billing?checkout=<id>`, which asks the API how it went;
	 * nothing the redirect says is trusted. Without a publishable key the API
	 * returns no form config, and the owner pays on Moyasar's hosted page.
	 *
	 * Needs `manage_subscription` (owner); the API checks it again.
	 */
	import { untrack } from 'svelte';
	import { resolve } from '$app/paths';
	import { accessStore } from '$lib/stores/access.svelte.js';
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { businessStore } from '$lib/stores/business.svelte.js';
	import { ApiError } from '$lib/api/client.js';
	import { formatApiError } from '$lib/utils/errors.js';
	import { formatMoney } from '$lib/utils/money.js';
	import { listPlans, startPlanCheckout } from '$lib/api/billing.js';
	import {
		featureLabel,
		formatDay,
		lastDayOf,
		planName,
		planTagline
	} from '$lib/components/billing/plans.js';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import NoAccess from '$lib/components/ui/NoAccess.svelte';
	import MoyasarForm from '$lib/components/payment/MoyasarForm.svelte';

	let tenantId = $derived(tenantStore.activeTenantId);
	let businessId = $derived(businessStore.activeBusinessId);
	let allowed = $derived(accessStore.can('manage_subscription'));

	/** @type {import('$lib/api/billing.js').PlanCheckout | null} */
	let checkout = $state(null);
	/** @type {import('$lib/api/billing.js').Plan | null} */
	let plan = $state(null);
	let loading = $state(true);
	let nothingToPay = $state(false);
	/** @type {string | null} */
	let errorMessage = $state(null);
	let opened = false;

	async function open() {
		const tenant = tenantId;
		const business = businessId;
		if (!tenant || !business) return;
		loading = true;
		errorMessage = null;
		nothingToPay = false;
		try {
			const [started, plans] = await Promise.all([
				startPlanCheckout(
					tenant,
					business,
					new URL(resolve('/app/billing'), window.location.origin).href
				),
				listPlans(tenant)
					.then((page) => page.items)
					.catch(() => /** @type {import('$lib/api/billing.js').Plan[]} */ ([]))
			]);
			if (!started.checkout) {
				// No publishable key here: pay on Moyasar's own page instead.
				if (started.redirect_url?.startsWith('https://')) {
					window.location.assign(started.redirect_url);
					return;
				}
				throw new Error(t('The payment page could not be opened. Try again.'));
			}
			checkout = started;
			plan = plans.find((p) => p.tier === started.tier) ?? null;
		} catch (err) {
			if (err instanceof ApiError && err.code === 'subscription_not_awaiting_payment') {
				nothingToPay = true;
			} else {
				errorMessage = formatApiError(err);
			}
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (opened || !allowed || !tenantId || !businessId) return;
		opened = true;
		untrack(open);
	});

	let period = $derived.by(() => {
		const open = /** @type {import('$lib/api/billing.js').PlanCheckout | null} */ (checkout);
		if (!open) return '';
		return t('{from} – {to}', {
			from: formatDay(open.covers_from),
			to: formatDay(lastDayOf(open.covers_until))
		});
	});
</script>

<svelte:head>
	<title>{t('Checkout')} · NOVA</title>
</svelte:head>

<div class="mb-4">
	<Button size="sm" variant="ghost" href={resolve('/app/billing')}>
		<Icon name="arrow-right" class="size-3.5 rotate-180 rtl:rotate-0" />
		{t('Back to billing')}
	</Button>
</div>

<PageHeader
	eyebrow={t('Billing')}
	title={t('Checkout')}
	subtitle={t('Your plan starts as soon as the payment is confirmed.')}
/>

{#if !accessStore.loaded}
	<Skeleton class="h-96 rounded-panel" />
{:else if !allowed}
	<NoAccess what={t('checkout')} />
{:else if !businessId}
	<Alert tone="info">{t('Set up your storefront in Catalog first.')}</Alert>
{:else if loading}
	<div class="grid gap-6 lg:grid-cols-[1.25fr_1fr]">
		<Skeleton class="h-96 rounded-panel" />
		<Skeleton class="h-80 rounded-panel" />
	</div>
{:else if nothingToPay}
	<Card padding="lg" class="mx-auto max-w-lg text-center">
		<div
			class="mx-auto mb-4 flex size-12 items-center justify-center rounded-full bg-accent-soft text-accent"
		>
			<Icon name="check" class="size-6" />
		</div>
		<p class="font-semibold text-fg">{t('Nothing to pay right now')}</p>
		<p class="mt-1 text-sm text-fg-muted">
			{t('Your plan is already paid for, or it is free.')}
		</p>
		<Button class="mt-5" href={resolve('/app/billing')}>{t('Back to billing')}</Button>
	</Card>
{:else if errorMessage || !checkout}
	<Alert tone="error">
		<div class="flex flex-wrap items-center justify-between gap-3">
			<span>{errorMessage ?? t('The payment page could not be opened. Try again.')}</span>
			<Button size="sm" variant="outline" onclick={open}>{t('Try again')}</Button>
		</div>
	</Alert>
{:else}
	<div class="grid items-start gap-6 lg:grid-cols-[1.25fr_1fr]">
		<!-- Payment -->
		<Card padding="none" class="overflow-hidden rounded-panel">
			<div class="border-b border-line px-6 py-5">
				<p class="font-semibold text-fg">{t('Payment details')}</p>
				<p class="mt-0.5 text-sm text-fg-muted">
					{t('Pay by card (mada, Visa, Mastercard) or STC Pay.')}
				</p>
			</div>
			<div class="p-6">
				{#if checkout.checkout}
					<MoyasarForm config={checkout.checkout} />
				{/if}
			</div>
		</Card>

		<!-- What is being bought -->
		<Card padding="none" class="overflow-hidden rounded-panel lg:sticky lg:top-6">
			<div class="bg-surface-sunken px-6 py-5">
				<div class="flex items-center justify-between gap-3">
					<p class="text-xs font-medium tracking-wide text-fg-muted uppercase">
						{t('Order summary')}
					</p>
					<Badge>{checkout.annual ? t('Annual') : t('Monthly')}</Badge>
				</div>
				<p class="mt-2 text-xl font-semibold tracking-tight text-fg">
					{t('{plan} plan', { plan: planName(checkout.tier) })}
				</p>
				{#if planTagline(checkout.tier)}
					<p class="mt-0.5 text-sm text-fg-muted">{planTagline(checkout.tier)}</p>
				{/if}
			</div>

			<div class="space-y-5 px-6 py-5">
				{#if plan?.included_features?.length}
					<ul class="space-y-2">
						{#each plan.included_features.slice(0, 6) as feature (feature)}
							<li class="flex items-start gap-2 text-sm text-fg-secondary">
								<Icon name="check" class="mt-0.5 size-4 shrink-0 text-accent" />
								{featureLabel(feature)}
							</li>
						{/each}
					</ul>
				{/if}

				<dl class="space-y-2.5 border-t border-line pt-5 text-sm">
					<div class="flex items-center justify-between gap-3">
						<dt class="text-fg-muted">{t('Covers')}</dt>
						<dd class="text-end text-fg">{period}</dd>
					</div>
					<div class="flex items-center justify-between gap-3">
						<dt class="text-fg-muted">{t('Plan price')}</dt>
						<dd class="text-fg tabular-nums">
							{formatMoney(checkout.net_amount, checkout.currency)}
						</dd>
					</div>
					<div class="flex items-center justify-between gap-3">
						<dt class="text-fg-muted">{t('VAT (15%)')}</dt>
						<dd class="text-fg tabular-nums">
							{formatMoney(checkout.vat_amount, checkout.currency)}
						</dd>
					</div>
					<div class="flex items-center justify-between gap-3 border-t border-line pt-3">
						<dt class="font-semibold text-fg">{t('Total due today')}</dt>
						<dd class="text-lg font-semibold text-fg tabular-nums">
							{formatMoney(checkout.total_amount, checkout.currency)}
						</dd>
					</div>
				</dl>

				<p class="flex gap-2 rounded-control bg-surface-sunken p-3 text-xs text-fg-secondary">
					<Icon name="info" class="mt-px size-3.5 shrink-0" />
					{t(
						'You can change or cancel your plan any time from Billing. A tax invoice is issued for every payment.'
					)}
				</p>
			</div>
		</Card>
	</div>
{/if}
