<script>
	import { accessStore } from '$lib/stores/access.svelte.js';
	import NoAccess from '$lib/components/ui/NoAccess.svelte';
	/**
	 * KPIs, the chart catalog (docs/13 section 7, rendered with layerchart via
	 * `ChartPanel`), a breakdown table, and — for those with `view_financials`
	 * too — the financial summary. Gated server-side by `view_analytics`; a
	 * receptionist or provider reaching this page simply gets each call's own
	 * 403 back, which reads here as an inline message rather than a crash.
	 *
	 * Some charts are plan-gated (`Chart.required_feature`, docs/11 section 2).
	 * Rather than call each one and let it 403, this reads the catalog against
	 * the business's own plan features first and renders a locked card with a
	 * link to Billing — the same "no subscription yet" default the billing
	 * page assumes (`subscription_or_default`: a business that never
	 * subscribed is Solo).
	 */
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { businessStore } from '$lib/stores/business.svelte.js';
	import { errorMessage } from '$lib/utils/errors.js';
	import { formatMoney, formatPercent } from '$lib/utils/money.js';
	import { ApiError } from '$lib/api/client.js';
	import { listPlans, getSubscription } from '$lib/api/billing.js';
	import { listCharts, getOverview, getBreakdown } from '$lib/api/analytics.js';

	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import KpiTile from '$lib/components/analytics/KpiTile.svelte';
	import ChartPanel from '$lib/components/analytics/ChartPanel.svelte';
	import { resolve } from '$app/paths';

	let tenantId = $derived(/** @type {string} */ (tenantStore.activeTenantId));
	let businessId = $derived(businessStore.activeBusinessId);
	let allowed = $derived(accessStore.can('view_analytics'));

	const RANGE_PRESETS = [
		{ days: 7, label: 'Last 7 days' },
		{ days: 30, label: 'Last 30 days' },
		{ days: 90, label: 'Last 90 days' }
	];
	let rangeDays = $state(30);
	// These endpoints take a plain date (YYYY-MM-DD), not a datetime — unlike
	// booking.js and queue.js, which take full ISO instants throughout.
	let dateRange = $derived.by(() => {
		const now = new Date();
		const from = new Date(now.getTime() - rangeDays * 24 * 60 * 60 * 1000);
		return { dateFrom: from.toISOString().slice(0, 10), dateTo: now.toISOString().slice(0, 10) };
	});

	let loading = $state(true);
	let loadErrorMessage = $state(/** @type {string|null} */ (null));
	let includedFeatures = $state(/** @type {Set<string>} */ (new Set()));
	let charts = $state(/** @type {import('$lib/api/analytics.js').ChartCatalogEntry[]} */ ([]));
	let overview = $state(/** @type {import('$lib/api/analytics.js').Overview|null} */ (null));

	async function loadAll() {
		const currentBusinessId = businessId;
		if (!currentBusinessId) return;
		loading = true;
		loadErrorMessage = null;
		try {
			const [plansPage, chartsPage, overviewResult] = await Promise.all([
				listPlans(tenantId),
				listCharts(tenantId),
				getOverview(tenantId, currentBusinessId, dateRange)
			]);
			charts = chartsPage.items;
			overview = overviewResult;

			let tier = 'solo';
			try {
				tier = (await getSubscription(tenantId, currentBusinessId)).tier;
			} catch (err) {
				if (!(err instanceof ApiError && err.status === 404)) throw err;
			}
			const plan = plansPage.items.find((p) => p.tier === tier);
			includedFeatures = new Set(plan?.included_features ?? []);
		} catch (err) {
			loadErrorMessage = errorMessage(err);
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (businessId && allowed) loadAll();
	});

	// --- Breakdown -----------------------------------------------------------------

	/** @type {{ value: import('$lib/api/analytics.js').Dimension, label: string }[]} */
	const DIMENSIONS = [
		{ value: 'service', label: 'Service' },
		{ value: 'provider', label: 'Provider' },
		{ value: 'source', label: 'Source' },
		{ value: 'location', label: 'Branch' }
	];
	let dimension = $state(/** @type {import('$lib/api/analytics.js').Dimension} */ ('service'));
	let breakdown = $state(/** @type {import('$lib/api/analytics.js').BreakdownRow[]} */ ([]));
	let breakdownLoading = $state(false);
	let breakdownErrorMessage = $state(/** @type {string|null} */ (null));

	async function loadBreakdown() {
		const currentBusinessId = businessId;
		if (!currentBusinessId) return;
		breakdownLoading = true;
		breakdownErrorMessage = null;
		try {
			const page = await getBreakdown(tenantId, currentBusinessId, dimension, dateRange);
			breakdown = page.items;
		} catch (err) {
			breakdownErrorMessage = errorMessage(err);
		} finally {
			breakdownLoading = false;
		}
	}

	$effect(() => {
		if (businessId && allowed) loadBreakdown();
	});
</script>

<svelte:head><title>Analytics — NOVA</title></svelte:head>

<PageHeader
	eyebrow="Business"
	title="Analytics"
	subtitle="What the numbers say about this business."
>
	{#snippet actions()}
		{#if businessId && allowed}
			<div class="w-44">
				<Select
					aria-label="Date range"
					bind:value={rangeDays}
					options={RANGE_PRESETS.map((p) => ({ value: p.days, label: p.label }))}
				/>
			</div>
		{/if}
	{/snippet}
</PageHeader>

{#if !allowed}
	<NoAccess what="analytics" />
{:else if !businessId}
	<Alert tone="info">Set up your storefront in Catalog first.</Alert>
{:else}
	{#if loading}
		<div class="flex justify-center py-12"><Spinner /></div>
	{:else if loadErrorMessage}
		<Alert tone="error">{loadErrorMessage}</Alert>
	{:else}
		{#if overview}
			<section class="mb-8">
				<div class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
					{#each overview.kpis as kpi (kpi.metric)}
						<KpiTile {kpi} currency={overview.currency} />
					{/each}
				</div>
			</section>
		{/if}

		<section class="mb-8">
			<h2 class="mb-3 text-base font-semibold tracking-tight text-fg">Charts</h2>
			{#if charts.length === 0}
				<EmptyState title="No charts available" />
			{:else}
				<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
					{#each charts as entry (entry.chart_id)}
						{@const locked =
							entry.required_feature && !includedFeatures.has(entry.required_feature)}
						<Card padding="md" class="min-w-0">
							{#if locked}
								<p class="text-sm font-semibold text-fg">
									{entry.title_en}
								</p>
								<p class="mt-1 text-sm text-fg-muted">{entry.question_en}</p>
								<Alert tone="info" class="mt-3">
									Not included in your current plan.
									<a href={resolve('/app/billing')} class="font-medium text-accent hover:underline">
										Upgrade to unlock
									</a>
								</Alert>
							{:else}
								<ChartPanel
									{tenantId}
									{businessId}
									chartId={entry.chart_id}
									dateFrom={dateRange.dateFrom}
									dateTo={dateRange.dateTo}
								/>
							{/if}
						</Card>
					{/each}
				</div>
			{/if}
		</section>

		<section>
			<div class="mb-3 flex items-center justify-between">
				<h2 class="text-base font-semibold tracking-tight text-fg">Breakdown</h2>
				<div class="w-40">
					<Select bind:value={dimension} options={DIMENSIONS} />
				</div>
			</div>
			{#if breakdownLoading}
				<div class="flex justify-center py-8"><Spinner /></div>
			{:else if breakdownErrorMessage}
				<Alert tone="error">{breakdownErrorMessage}</Alert>
			{:else if breakdown.length === 0}
				<EmptyState title="Nothing in this window" />
			{:else}
				<Card padding="none" class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead>
							<tr class="border-b border-line bg-surface-sunken text-start text-xs text-fg-muted">
								<th class="px-4 py-2.5 text-start font-medium">
									{DIMENSIONS.find((d) => d.value === dimension)?.label}
								</th>
								<th class="px-4 py-2.5 text-start font-medium">Bookings</th>
								<th class="px-4 py-2.5 text-start font-medium">Completed</th>
								<th class="px-4 py-2.5 text-start font-medium">Revenue</th>
								<th class="px-4 py-2.5 text-start font-medium">Share</th>
							</tr>
						</thead>
						<tbody
							class="divide-y divide-line-subtle [&_tr]:transition-colors [&_tr:hover]:bg-surface-sunken"
						>
							{#each breakdown as row (row.key)}
								<tr>
									<td class="px-4 py-3 font-medium text-fg">{row.label}</td>
									<td class="px-4 py-3 text-fg-secondary tabular-nums">{row.bookings}</td>
									<td class="px-4 py-3 text-fg-secondary tabular-nums">{row.completed}</td>
									<td class="px-4 py-3 text-fg-secondary tabular-nums">
										{formatMoney(row.revenue, overview?.currency ?? 'SAR', 'en')}
									</td>
									<td class="px-4 py-3 text-fg-secondary tabular-nums">
										{row.share_of_revenue !== null
											? formatPercent(row.share_of_revenue, { locale: 'en' })
											: '—'}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</Card>
			{/if}
		</section>
	{/if}
{/if}
