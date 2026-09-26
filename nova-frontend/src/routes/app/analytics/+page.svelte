<script>
	import { t, m, i18n, intlLocale } from '$lib/i18n/index.svelte.js';
	/**
	 * The business's numbers for one window, compared with the window before
	 * it: a headline row (revenue as the hero figure, then bookings,
	 * completion and new customers), then one section per question the owner
	 * asks (money in, bookings, customers, the floor, fees), each with its own
	 * KPIs and charts from the catalog (docs/13 section 7), and a breakdown
	 * table last.
	 *
	 * Gated server-side by `view_analytics`; the page is hidden from roles
	 * without it (`accessStore`). Plan-gated charts (`required_feature`,
	 * docs/11 section 2) are read against the business's plan first and shown
	 * locked rather than requested only to 403 — a business that never
	 * subscribed is Solo (`subscription_or_default`).
	 */
	import { resolve } from '$app/paths';
	import { accessStore } from '$lib/stores/access.svelte.js';
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { businessStore } from '$lib/stores/business.svelte.js';
	import { errorMessage } from '$lib/utils/errors.js';
	import { ApiError } from '$lib/api/client.js';
	import { listPlans, getSubscription } from '$lib/api/billing.js';
	import { listCharts, getOverview, getBreakdown, getChart } from '$lib/api/analytics.js';
	import { chartModel } from '$lib/utils/chartData.js';

	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import NoAccess from '$lib/components/ui/NoAccess.svelte';
	import KpiTile from '$lib/components/analytics/KpiTile.svelte';
	import ChartPanel from '$lib/components/analytics/ChartPanel.svelte';
	import { formatKpi, kpiDelta } from '$lib/components/analytics/kpis.js';
	import { formatValue } from '$lib/components/analytics/viz/format.js';
	import Sparkline from '$lib/components/analytics/viz/Sparkline.svelte';

	let tenantId = $derived(/** @type {string} */ (tenantStore.activeTenantId));
	let businessId = $derived(businessStore.activeBusinessId);
	let allowed = $derived(accessStore.can('view_analytics'));

	// --- The window ---------------------------------------------------------------

	const RANGES = [
		{ days: 7, label: m('7 days') },
		{ days: 30, label: m('30 days') },
		{ days: 90, label: m('90 days') }
	];
	let rangeDays = $state(30);

	/** @param {Date} date */
	const iso = (date) => date.toISOString().slice(0, 10);
	/** @param {string} day @param {number} offset */
	const shift = (day, offset) => iso(new Date(Date.parse(`${day}T00:00:00Z`) + offset * 864e5));

	// Plain dates (YYYY-MM-DD): these endpoints declare `date`, not `datetime`.
	// Both windows are `rangeDays` long, inclusive, the previous one ending the
	// day before the current one starts.
	let windows = $derived.by(() => {
		const dateTo = iso(new Date());
		const dateFrom = shift(dateTo, -(rangeDays - 1));
		const previousTo = shift(dateFrom, -1);
		return {
			current: { dateFrom, dateTo },
			previous: { dateFrom: shift(previousTo, -(rangeDays - 1)), dateTo: previousTo }
		};
	});
	let compareLabel = $derived(t('vs previous {count} days', { count: rangeDays }));

	/** @param {string} day */
	const shortDate = (day) =>
		new Intl.DateTimeFormat(intlLocale(), {
			day: 'numeric',
			month: 'short',
			timeZone: 'UTC'
		}).format(Date.parse(`${day}T00:00:00Z`));

	// --- Overview, catalog and plan -------------------------------------------------

	let loading = $state(true);
	let loadErrorMessage = $state(/** @type {string|null} */ (null));
	let includedFeatures = $state(/** @type {string[]} */ ([]));
	let charts = $state(/** @type {import('$lib/api/analytics.js').ChartCatalogEntry[]} */ ([]));
	let overview = $state(/** @type {import('$lib/api/analytics.js').Overview|null} */ (null));
	let previous = $state(/** @type {import('$lib/api/analytics.js').Overview|null} */ (null));

	$effect(() => {
		const business = businessId;
		const tenant = tenantId;
		const { current, previous: before } = windows;
		if (!business || !allowed) return;
		let cancelled = false;
		loading = true;
		loadErrorMessage = null;
		Promise.all([
			getOverview(tenant, business, current),
			// The comparison is extra: without it the page still stands.
			getOverview(tenant, business, before).catch(() => null)
		])
			.then(([now, then]) => {
				if (cancelled) return;
				overview = now;
				previous = then;
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

	$effect(() => {
		const business = businessId;
		const tenant = tenantId;
		if (!business || !allowed) return;
		Promise.all([listCharts(tenant), listPlans(tenant), planTier(tenant, business)])
			.then(([catalog, plans, tier]) => {
				charts = catalog.items;
				includedFeatures = plans.items.find((p) => p.tier === tier)?.included_features ?? [];
			})
			.catch((err) => (loadErrorMessage = errorMessage(err)));
	});

	/** @param {string} tenant @param {string} business */
	async function planTier(tenant, business) {
		try {
			return (await getSubscription(tenant, business)).tier;
		} catch (err) {
			if (err instanceof ApiError && err.status === 404) return 'solo';
			throw err;
		}
	}

	/** @param {string} metric */
	const kpi = (metric) => overview?.kpis.find((k) => k.metric === metric);
	/** @param {string} metric */
	const prev = (metric) => previous?.kpis.find((k) => k.metric === metric);
	let currency = $derived(overview?.currency ?? 'SAR');

	// --- Sections -------------------------------------------------------------------

	/**
	 * Which KPIs and charts answer which question. A chart the catalog lists
	 * that no section claims still shows, under the last section.
	 */
	const SECTIONS = [
		{
			id: 'revenue',
			title: m('Revenue'),
			lead: m('What came in, and from what.'),
			kpis: ['average_ticket', 'collected', 'prepaid_share', 'refunded'],
			charts: ['revenue_trend', 'revenue_by_service', 'revenue_by_provider', 'revenue_by_location']
		},
		{
			id: 'bookings',
			title: m('Bookings'),
			lead: m('How many, how they ended, and where they came from.'),
			kpis: ['completed', 'cancellation_rate', 'no_show_rate', 'median_lead_time_hours'],
			charts: ['bookings_trend', 'booking_outcomes', 'source_mix', 'bookings_forecast']
		},
		{
			id: 'customers',
			title: m('Customers'),
			lead: m('Who is new, who comes back, and who has drifted away.'),
			kpis: ['unique_customers', 'returning_customers', 'repeat_rate', 'lapsed_customers'],
			charts: ['new_vs_returning', 'retention_cohorts']
		},
		{
			id: 'operations',
			title: m('Operations'),
			lead: m('How full the chairs are, and when.'),
			kpis: ['utilization', 'walk_ins', 'average_queue_wait_minutes', 'marketplace_share'],
			charts: ['peak_hours', 'provider_utilization', 'queue_wait_times']
		},
		{
			id: 'fees',
			title: m('Payouts & fees'),
			lead: m('What reached your account, and what NOVA charged.'),
			kpis: [],
			charts: ['payouts_breakdown', 'nova_charges', 'commission_by_class']
		}
	];

	/** Charts that read best across the full width: time series and grids. */
	const WIDE = new Set([
		'revenue_trend',
		'bookings_trend',
		'peak_hours',
		'new_vs_returning',
		'queue_wait_times',
		'retention_cohorts'
	]);

	let sections = $derived.by(() => {
		const claimed = new Set(SECTIONS.flatMap((s) => s.charts));
		const byId = new Map(charts.map((c) => [c.chart_id, c]));
		return SECTIONS.map((section, i) => ({
			...section,
			entries: [
				...section.charts.flatMap((id) => byId.get(id) ?? []),
				...(i === SECTIONS.length - 1 ? charts.filter((c) => !claimed.has(c.chart_id)) : [])
			]
		}))
			.map((section) => ({ ...section, wide: spans(section.entries) }))
			.filter((section) => section.entries.length || section.kpis.length);
	});

	/**
	 * Wide charts span the row; so does a half-width chart left alone at the
	 * end of its run, rather than leaving a hole beside it.
	 * @param {import('$lib/api/analytics.js').ChartCatalogEntry[]} entries
	 */
	function spans(entries) {
		/** @type {boolean[]} */
		const wide = [];
		let run = 0;
		entries.forEach((entry, i) => {
			if (WIDE.has(entry.chart_id)) {
				if (run % 2 === 1) wide[i - 1] = true;
				wide.push(true);
				run = 0;
			} else {
				wide.push(false);
				run += 1;
			}
		});
		if (run % 2 === 1) wide[wide.length - 1] = true;
		return wide;
	}

	/** @param {import('$lib/api/analytics.js').ChartCatalogEntry} entry */
	const isLocked = (entry) =>
		!!entry.required_feature && !includedFeatures.includes(entry.required_feature);

	// --- Sparklines ------------------------------------------------------------------

	/**
	 * Per-day values behind the headline figures, read from the same charts
	 * the sections draw. Decoration only: a chart that fails leaves its
	 * figure without a line, never the page with an error.
	 * @type {Record<string, (number|null)[]>}
	 */
	let trends = $state({});
	const TREND_SOURCES = [
		{ metric: 'revenue', chart: 'revenue_trend', series: [0] },
		{ metric: 'bookings', chart: 'bookings_trend', series: [0, 1, 2, 3] },
		{ metric: 'new_customers', chart: 'new_vs_returning', series: [0] }
	];

	$effect(() => {
		const business = businessId;
		const tenant = tenantId;
		const range = windows.current;
		if (!business || !allowed) return;
		let cancelled = false;
		for (const source of TREND_SOURCES) {
			getChart(tenant, source.chart, { businessId: business, ...range })
				.then((chart) => {
					const model = chartModel(chart);
					const columns = model?.type === 'combo' ? model.columns : model;
					if (cancelled || columns?.type !== 'columns') return;
					trends[source.metric] = columns.categories.map((_, i) =>
						source.series.reduce((sum, s) => sum + (columns.series[s]?.values[i] ?? 0), 0)
					);
				})
				.catch(() => {
					if (!cancelled) delete trends[source.metric];
				});
		}
		return () => {
			cancelled = true;
		};
	});

	// --- Hero -----------------------------------------------------------------------

	let heroValue = $derived(formatKpi(kpi('revenue'), { currency }));
	let heroDelta = $derived(kpiDelta(kpi('revenue'), prev('revenue')));

	// --- Breakdown ------------------------------------------------------------------

	/** @type {{ value: import('$lib/api/analytics.js').Dimension, label: string }[]} */
	const DIMENSIONS = [
		{ value: 'service', label: m('Service') },
		{ value: 'provider', label: m('Team member') },
		{ value: 'source', label: m('Source') },
		{ value: 'location', label: m('Branch') }
	];
	let dimension = $state(/** @type {import('$lib/api/analytics.js').Dimension} */ ('service'));
	let breakdown = $state(/** @type {import('$lib/api/analytics.js').BreakdownRow[]|null} */ (null));
	let breakdownLoading = $state(false);
	let breakdownErrorMessage = $state(/** @type {string|null} */ (null));

	$effect(() => {
		const business = businessId;
		const tenant = tenantId;
		const dim = dimension;
		const range = windows.current;
		if (!business || !allowed) return;
		let cancelled = false;
		breakdownLoading = true;
		breakdownErrorMessage = null;
		// Row labels (service, source...) come back in the page's language.
		getBreakdown(tenant, business, dim, { ...range, locale: i18n.locale })
			.then((page) => {
				if (!cancelled) breakdown = page.items;
			})
			.catch((err) => {
				if (!cancelled) breakdownErrorMessage = errorMessage(err);
			})
			.finally(() => {
				if (!cancelled) breakdownLoading = false;
			});
		return () => {
			cancelled = true;
		};
	});

	let breakdownMax = $derived(Math.max(0, ...(breakdown ?? []).map((row) => Number(row.revenue))));

	/** @param {KeyboardEvent} event @param {number} index */
	function rangeKey(event, index) {
		const step = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: 1, ArrowUp: -1 }[event.key];
		if (!step) return;
		event.preventDefault();
		const next = RANGES[(index + step + RANGES.length) % RANGES.length];
		rangeDays = next.days;
		/** @type {HTMLElement|null} */ (
			/** @type {HTMLElement} */ (event.currentTarget).parentElement?.querySelector(
				`[data-days="${next.days}"]`
			)
		)?.focus();
	}
</script>

<svelte:head><title>{t('Analytics')} — NOVA</title></svelte:head>

<PageHeader
	eyebrow={t('Business')}
	title={t('Analytics')}
	subtitle={t('How the business is doing, and why.')}
/>

{#if !allowed}
	<NoAccess what={t('analytics')} />
{:else if !businessId}
	<Alert tone="info">{t('Set up your storefront in Catalog first.')}</Alert>
{:else}
	<!-- Filters: one row, above everything they change. -->
	<div
		class="sticky top-14 z-20 -mx-4 mb-6 flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-canvas/85 px-4 py-3 backdrop-blur-xl sm:-mx-6 sm:px-6 lg:top-0 lg:-mx-10 lg:px-10"
	>
		<div
			class="inline-flex gap-1 rounded-control bg-surface-muted p-1"
			role="radiogroup"
			aria-label={t('Date range')}
		>
			{#each RANGES as range, index (range.days)}
				<button
					type="button"
					role="radio"
					data-days={range.days}
					aria-checked={rangeDays === range.days}
					tabindex={rangeDays === range.days ? 0 : -1}
					onclick={() => (rangeDays = range.days)}
					onkeydown={(event) => rangeKey(event, index)}
					class={[
						'h-8 rounded-[calc(var(--radius-control)-2px)] px-3.5 text-sm font-medium whitespace-nowrap focus-ring transition-[background-color,color,box-shadow] duration-fast',
						rangeDays === range.days
							? 'bg-surface text-fg shadow-card ring-1 ring-line dark:bg-slate-700/60 dark:ring-white/5'
							: 'text-fg-muted hover:text-fg'
					].join(' ')}
				>
					{t(range.label)}
				</button>
			{/each}
		</div>
		<p class="text-sm text-fg-muted">
			<span class="font-medium text-fg-secondary"
				>{shortDate(windows.current.dateFrom)} – {shortDate(windows.current.dateTo)}</span
			>
			<span class="hidden sm:inline">
				· {t('compared with {from} – {to}', {
					from: shortDate(windows.previous.dateFrom),
					to: shortDate(windows.previous.dateTo)
				})}</span
			>
		</p>
		{#if loading && overview}
			<span class="ms-auto flex items-center gap-2 text-xs text-fg-subtle" role="status">
				<span class="size-1.5 animate-pulse rounded-full bg-accent"></span>
				{t('Updating')}
			</span>
		{/if}
		{#if sections.length}
			<nav
				aria-label={t('Sections')}
				class="-mb-1 flex w-full [scrollbar-width:none] gap-1 overflow-x-auto pb-1"
			>
				{#each sections as section (section.id)}
					<a
						href={`#${section.id}`}
						class="shrink-0 rounded-full px-3 py-1 text-[13px] font-medium text-fg-muted focus-ring transition-colors hover:bg-surface-muted hover:text-fg"
						>{t(section.title)}</a
					>
				{/each}
				<a
					href="#breakdown"
					class="shrink-0 rounded-full px-3 py-1 text-[13px] font-medium text-fg-muted focus-ring transition-colors hover:bg-surface-muted hover:text-fg"
					>{t('Breakdown')}</a
				>
			</nav>
		{/if}
	</div>

	{#if loadErrorMessage && !overview}
		<Alert tone="error">{loadErrorMessage}</Alert>
	{:else if !overview}
		<div class="grid gap-4 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
			<Skeleton class="h-44 rounded-card" />
			<Skeleton class="h-44 rounded-card" />
			<Skeleton class="h-44 rounded-card" />
			<Skeleton class="h-44 rounded-card" />
		</div>
	{:else}
		<div class={['transition-opacity duration-base', loading ? 'opacity-60' : ''].join(' ')}>
			<!-- Headline -->
			<section aria-label={t('Headline')} class="grid gap-4 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
				<div
					class="relative overflow-hidden rounded-card border border-line bg-surface p-6 shadow-card"
				>
					<div
						class="pointer-events-none absolute -end-16 -top-16 size-48 rounded-full bg-accent-soft blur-2xl"
						aria-hidden="true"
					></div>
					<p class="relative flex items-center gap-2 text-sm font-medium text-fg-muted">
						{t('Revenue')}
						<span class="text-fg-subtle">· {t('{count} days', { count: rangeDays })}</span>
					</p>
					{#if heroValue}
						<p class="relative mt-3 text-5xl font-semibold tracking-tight text-fg">{heroValue}</p>
					{:else}
						<p class="relative mt-3 text-5xl font-semibold tracking-tight text-fg-subtle">—</p>
					{/if}
					<p class="relative mt-3 flex flex-wrap items-center gap-2 text-sm">
						{#if heroDelta}
							<span
								class={[
									'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold',
									heroDelta.tone === 'good'
										? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400'
										: heroDelta.tone === 'bad'
											? 'bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400'
											: 'bg-surface-muted text-fg-muted'
								].join(' ')}
							>
								<Icon
									name={heroDelta.direction > 0
										? 'arrow-up'
										: heroDelta.direction < 0
											? 'arrow-down'
											: 'minus'}
									class="size-3"
								/>
								{heroDelta.text}
							</span>
							<span class="text-fg-muted">{compareLabel}</span>
						{/if}
					</p>
					{#if trends.revenue}
						<div class="relative mt-4"><Sparkline values={trends.revenue} height={48} /></div>
					{/if}
					<dl class="relative mt-4 grid grid-cols-2 gap-4 border-t border-line-subtle pt-4 text-sm">
						<div>
							<dt class="text-fg-muted">{t('Average ticket')}</dt>
							<dd class="mt-0.5 font-medium text-fg">
								{formatKpi(kpi('average_ticket'), { currency }) ?? '—'}
							</dd>
						</div>
						<div>
							<dt class="text-fg-muted">{t('Collected online')}</dt>
							<dd class="mt-0.5 font-medium text-fg">
								{formatKpi(kpi('collected'), { currency }) ?? '—'}
							</dd>
						</div>
					</dl>
				</div>
				{#each ['bookings', 'completion_rate', 'new_customers'] as metric (metric)}
					{@const value = kpi(metric)}
					<div
						class="flex flex-col justify-between gap-4 rounded-card border border-line bg-surface p-5 shadow-card"
					>
						<KpiTile kpi={value} previous={prev(metric)} {currency} {compareLabel} />
						{#if value?.unit === 'ratio' && value.value !== null}
							<div class="h-1.5 overflow-hidden rounded-full bg-surface-muted" role="presentation">
								<div
									class="h-full rounded-full bg-[var(--chart-status-good)]"
									style:width={`${Number(value.value) * 100}%`}
								></div>
							</div>
						{:else if trends[metric]}
							<Sparkline values={trends[metric]} />
						{/if}
					</div>
				{/each}
			</section>

			{#if overview.excluded_rows > 0}
				<p class="mt-3 flex items-center gap-1.5 text-xs text-fg-muted">
					<Icon name="info" class="size-3.5" />
					{t('{count} bookings in another currency are left out of these totals.', {
						count: overview.excluded_rows
					})}
				</p>
			{/if}

			<!-- One section per question -->
			{#each sections as section (section.id)}
				<section
					id={section.id}
					class="mt-12 scroll-mt-36"
					aria-labelledby={`${section.id}-heading`}
				>
					<div class="mb-4">
						<h2 id={`${section.id}-heading`} class="text-lg font-semibold tracking-tight text-fg">
							{t(section.title)}
						</h2>
						<p class="text-sm text-fg-muted">{t(section.lead)}</p>
					</div>

					{#if section.kpis.length}
						<div
							class="mb-4 grid grid-cols-2 divide-line-subtle overflow-hidden rounded-card border border-line bg-surface shadow-card lg:grid-cols-4 lg:divide-x [&>*]:border-line-subtle max-lg:[&>*:nth-child(-n+2)]:border-b max-lg:[&>*:nth-child(odd)]:border-e"
						>
							{#each section.kpis as metric (metric)}
								<div class="p-4 sm:p-5">
									<KpiTile
										kpi={kpi(metric)}
										previous={prev(metric)}
										{currency}
										{compareLabel}
										size="sm"
									/>
								</div>
							{/each}
						</div>
					{/if}

					{#if section.entries.length}
						<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
							{#each section.entries as entry, i (entry.chart_id)}
								<ChartPanel
									{tenantId}
									{businessId}
									{entry}
									{currency}
									dateFrom={windows.current.dateFrom}
									dateTo={windows.current.dateTo}
									locked={isLocked(entry)}
									class={section.wide[i] ? 'lg:col-span-2' : ''}
								/>
							{/each}
						</div>
					{/if}
				</section>
			{/each}

			<!-- Breakdown -->
			<section id="breakdown" class="mt-12 scroll-mt-36" aria-labelledby="breakdown-heading">
				<div class="mb-4 flex flex-wrap items-end justify-between gap-3">
					<div>
						<h2 id="breakdown-heading" class="text-lg font-semibold tracking-tight text-fg">
							{t('Breakdown')}
						</h2>
						<p class="text-sm text-fg-muted">{t('Every booking and riyal, split one way.')}</p>
					</div>
					<div
						class="inline-flex gap-1 rounded-control bg-surface-muted p-1"
						role="radiogroup"
						aria-label={t('Split by')}
					>
						{#each DIMENSIONS as option (option.value)}
							<button
								type="button"
								role="radio"
								aria-checked={dimension === option.value}
								onclick={() => (dimension = option.value)}
								class={[
									'h-7 rounded-[calc(var(--radius-control)-2px)] px-3 text-[13px] font-medium whitespace-nowrap focus-ring transition-[background-color,color,box-shadow] duration-fast',
									dimension === option.value
										? 'bg-surface text-fg shadow-card ring-1 ring-line dark:bg-slate-700/60 dark:ring-white/5'
										: 'text-fg-muted hover:text-fg'
								].join(' ')}
							>
								{t(option.label)}
							</button>
						{/each}
					</div>
				</div>

				{#if breakdownErrorMessage}
					<Alert tone="error">{breakdownErrorMessage}</Alert>
				{:else if breakdown === null}
					<Skeleton class="h-48 rounded-card" />
				{:else if breakdown.length === 0}
					<div
						class="flex flex-col items-center gap-2 rounded-card border border-line bg-surface p-10 text-center shadow-card"
					>
						<Icon name="chart-bar" class="size-5 text-fg-subtle" />
						<p class="text-sm text-fg-muted">{t('Nothing in this window yet.')}</p>
					</div>
				{:else}
					<div
						class={[
							'overflow-x-auto rounded-card border border-line bg-surface shadow-card transition-opacity duration-base',
							breakdownLoading ? 'opacity-60' : ''
						].join(' ')}
					>
						<table class="w-full min-w-[560px] text-sm">
							<thead>
								<tr class="border-b border-line bg-surface-sunken text-xs text-fg-muted">
									<th scope="col" class="px-5 py-2.5 text-start font-medium">
										{t(DIMENSIONS.find((d) => d.value === dimension)?.label ?? '')}
									</th>
									<th scope="col" class="px-4 py-2.5 text-end font-medium">{t('Bookings')}</th>
									<th scope="col" class="px-4 py-2.5 text-end font-medium">{t('Completed')}</th>
									<th scope="col" class="px-4 py-2.5 text-end font-medium">{t('Revenue')}</th>
									<th scope="col" class="w-48 px-5 py-2.5 text-start font-medium"
										>{t('Share of revenue')}</th
									>
								</tr>
							</thead>
							<tbody class="divide-y divide-line-subtle">
								{#each breakdown as row (row.key)}
									{@const share =
										row.share_of_revenue === null ? null : Number(row.share_of_revenue)}
									<tr class="transition-colors hover:bg-surface-sunken">
										<th scope="row" class="px-5 py-3 text-start font-medium text-fg">{row.label}</th
										>
										<td class="px-4 py-3 text-end text-fg-secondary tabular-nums">{row.bookings}</td
										>
										<td class="px-4 py-3 text-end text-fg-secondary tabular-nums"
											>{row.completed}</td
										>
										<td class="px-4 py-3 text-end font-medium text-fg tabular-nums">
											{formatValue(Number(row.revenue), 'money', { currency })}
										</td>
										<td class="px-5 py-3">
											<div class="flex items-center gap-3">
												<div class="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-muted">
													<div
														class="h-full rounded-full bg-[var(--chart-series-1)]"
														style:width={`${breakdownMax ? (Number(row.revenue) / breakdownMax) * 100 : 0}%`}
													></div>
												</div>
												<span class="w-12 text-end text-xs text-fg-muted tabular-nums">
													{share === null ? '—' : `${Math.round(share * 1000) / 10}%`}
												</span>
											</div>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</section>

			<p class="mt-10 text-xs text-fg-subtle">
				{t(
					"Numbers are in {currency}, for the business's own time zone ({timezone}). A dash means too few bookings to say anything reliable yet.",
					{ currency, timezone: overview.window.timezone }
				)}
				<a href={resolve('/app/billing')} class="text-accent hover:underline">{t('Plans')}</a>
				{t('unlock more charts.')}
			</p>
		</div>
	{/if}
{/if}
