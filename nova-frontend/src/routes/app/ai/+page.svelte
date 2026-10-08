<script>
	import { t, m } from '$lib/i18n/index.svelte.js';
	/**
	 * The staff AI workspace: the owner agents (docs/13), each answering from
	 * this business's live data through the same services the dashboard uses.
	 *
	 * - Which agents appear depends on this role's permissions in this
	 *   business (`accessStore`); the turn still checks for itself.
	 * - A plan-gated agent (`required_feature`) is shown with the plan that
	 *   unlocks it. When the business's plan lacks it (read from billing, which
	 *   every role with such an agent may read), it is shown locked with the way
	 *   to upgrade instead of a chat the backend would refuse.
	 * - Every figure in an answer came from a tool (the grounding guardrail),
	 *   and the business manager only proposes — nothing here changes data.
	 * - With the local model server offline the page says so, rather than
	 *   offering a chat that would only hand off.
	 */
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { businessStore } from '$lib/stores/business.svelte.js';
	import { accessStore } from '$lib/stores/access.svelte.js';
	import { listAgents } from '$lib/api/ai.js';
	import { listPlans, getSubscription } from '$lib/api/billing.js';
	import { ApiError } from '$lib/api/client.js';
	import { planName, tierRank } from '$lib/components/billing/plans.js';
	import { resolve } from '$app/paths';
	import { errorMessage } from '$lib/utils/errors.js';

	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import ChatWidget from '$lib/components/ai/ChatWidget.svelte';

	/**
	 * How each staff agent is presented. The roster itself comes from the API;
	 * an agent missing here still appears, under its goal.
	 * @type {Record<string, { label: string, blurb: string, icon: import('$lib/components/ui/Icon.svelte').IconName, starters: string[] }>}
	 */
	const PRESENTATION = {
		accountant_agent: {
			label: m('Accountant'),
			blurb: m('What you earned, collected and were paid out, and what NOVA charged.'),
			icon: 'receipt',
			starters: [
				m('How much did we earn last month?'),
				m('What did NOVA charge us this month?'),
				m('Show me our recent payouts.')
			]
		},
		analyst_agent: {
			label: m('Analyst'),
			blurb: m('Trends, busy hours, top services and providers, with charts.'),
			icon: 'chart-bar',
			starters: [
				m('How are bookings trending this quarter?'),
				m('Which services bring in the most revenue?'),
				m('When are our busiest hours?')
			]
		},
		business_manager_agent: {
			label: m('Business manager'),
			blurb: m('Advice grounded in your numbers. It proposes; you decide.'),
			icon: 'trending-up',
			starters: [
				m('What should we improve next month?'),
				m('Where are we losing bookings?'),
				m('How can we fill our quiet hours?')
			]
		}
	};

	let tenantId = $derived(tenantStore.activeTenantId);
	let businessId = $derived(businessStore.activeBusinessId);

	let loading = $state(true);
	let loadError = $state(/** @type {string|null} */ (null));
	let catalog = $state(/** @type {import('$lib/api/ai.js').AgentCatalog|null} */ (null));
	let selected = $state(/** @type {string|null} */ (null));
	/** Bumped to start a fresh conversation (a new session id). */
	let conversation = $state(0);

	function load() {
		if (!tenantId) return;
		const tenant = tenantId;
		loading = true;
		loadError = null;
		listAgents(tenant)
			.then((result) => {
				if (tenant === tenantId) catalog = result;
			})
			.catch((err) => (loadError = errorMessage(err)))
			.finally(() => (loading = false));
	}

	$effect(() => {
		load();
	});

	// --- What the business's plan unlocks ------------------------------------------

	let plans = $state(/** @type {import('$lib/api/billing.js').Plan[]} */ ([]));
	/** The tier whose terms are in force; null until known (nothing is locked then). */
	let tierInForce = $state(/** @type {string|null} */ (null));

	$effect(() => {
		const tenant = tenantId;
		const business = businessId;
		if (!tenant || !business || !accessStore.can('view_financials')) return;
		let cancelled = false;
		Promise.all([
			listPlans(tenant),
			getSubscription(tenant, business).catch((err) => {
				// Never subscribed: locked, and the dashboard sends the owner to Billing.
				if (err instanceof ApiError && err.status === 404) return null;
				throw err;
			})
		])
			.then(([page, subscription]) => {
				if (cancelled) return;
				plans = [...page.items].sort((a, b) => tierRank(a.tier) - tierRank(b.tier));
				// Unpaid after its trial: locked; the lowest tier locks every insights agent.
				tierInForce =
					!subscription || subscription.status === 'pending_payment' ? 'solo' : subscription.tier;
			})
			// Unknown is not locked: the backend still refuses a turn the plan lacks.
			.catch(() => {});
		return () => {
			cancelled = true;
		};
	});

	/** @param {import('$lib/api/ai.js').AgentInfo} agent */
	function locked(agent) {
		if (!agent.required_feature || !tierInForce) return false;
		const plan = plans.find((p) => p.tier === tierInForce);
		return !!plan && !plan.included_features.includes(agent.required_feature);
	}

	/** The cheapest plan that unlocks the agent. @param {import('$lib/api/ai.js').AgentInfo} agent */
	function unlockingTier(agent) {
		const feature = agent.required_feature;
		return plans.find((p) => feature && p.included_features.includes(feature))?.tier ?? 'studio';
	}

	let agents = $derived(
		(catalog?.agents ?? []).filter(
			(agent) =>
				agent.audience === 'staff' &&
				(!agent.required_permission || accessStore.can(agent.required_permission))
		)
	);

	// Keep a valid selection as the roster or the role loads.
	$effect(() => {
		if (!agents.some((agent) => agent.name === selected)) selected = agents[0]?.name ?? null;
	});

	let current = $derived(agents.find((agent) => agent.name === selected) ?? null);
	let presentation = $derived(current ? PRESENTATION[current.name] : null);

	/** @param {import('$lib/api/ai.js').AgentInfo} agent */
	function label(agent) {
		const known = PRESENTATION[agent.name];
		if (known) return t(known.label);
		const words = agent.name.replace(/_agent$/, '').replaceAll('_', ' ');
		return words.charAt(0).toUpperCase() + words.slice(1);
	}

	/** @param {string} name */
	function choose(name) {
		if (name === selected) return;
		selected = name;
		conversation += 1;
	}
</script>

<svelte:head><title>{t('AI assistant')} — NOVA</title></svelte:head>

<PageHeader
	eyebrow={t('Business')}
	title={t('AI assistant')}
	subtitle={t(
		'Ask about your business in plain language. Agents run on your own local model and answer only from your data.'
	)}
>
	{#snippet actions()}
		{#if current && !locked(current) && catalog?.inference_available}
			<Button variant="outline" size="sm" onclick={() => (conversation += 1)}>
				<Icon name="plus" class="size-4" />
				{t('New conversation')}
			</Button>
		{/if}
	{/snippet}
</PageHeader>

{#if !businessId}
	<Alert tone="info">{t('Set up your storefront in Catalog first.')}</Alert>
{:else if loadError}
	<Alert tone="error">{loadError}</Alert>
{:else if loading && !catalog}
	<div class="grid gap-6 lg:grid-cols-[17rem_minmax(0,1fr)]">
		<div class="space-y-2">
			{#each [0, 1, 2] as n (n)}<Skeleton class="h-20 rounded-card" />{/each}
		</div>
		<Skeleton class="h-[32rem] rounded-card" />
	</div>
{:else if catalog && !catalog.inference_available}
	<div class="rounded-card border border-line bg-surface p-6 shadow-card">
		<div class="flex items-start gap-4">
			<span
				class="flex size-10 shrink-0 items-center justify-center rounded-full bg-surface-muted text-fg-muted"
			>
				<Icon name="sparkles" class="size-5" />
			</span>
			<div class="min-w-0">
				<p class="font-semibold text-fg">{t('The AI model is offline')}</p>
				<p class="mt-1 max-w-2xl text-sm text-fg-secondary">
					{t(
						'NOVA could not reach its local model server. Start LM Studio (or Ollama) with a model available, then try again. Everything else in the dashboard keeps working.'
					)}
				</p>
				<Button class="mt-4" variant="outline" size="sm" onclick={load} {loading}>
					{t('Check again')}
				</Button>
			</div>
		</div>
	</div>
{:else if agents.length === 0}
	<Alert tone="info">{t('Your role has no AI agents in this business.')}</Alert>
{:else}
	<div class="grid items-start gap-6 lg:grid-cols-[17rem_minmax(0,1fr)]">
		<ul class="flex flex-col gap-2" aria-label={t('Agents')}>
			{#each agents as agent (agent.name)}
				{@const known = PRESENTATION[agent.name]}
				{@const active = agent.name === selected}
				<li>
					<button
						type="button"
						aria-pressed={active}
						onclick={() => choose(agent.name)}
						class={[
							'flex w-full items-start gap-3 rounded-card border p-3.5 text-start focus-ring transition-colors duration-fast',
							active
								? 'border-accent/40 bg-accent-soft/60 shadow-card'
								: 'border-line bg-surface hover:border-line-strong'
						].join(' ')}
					>
						<span
							class={[
								'flex size-9 shrink-0 items-center justify-center rounded-full',
								active ? 'bg-accent text-white' : 'bg-surface-muted text-fg-muted'
							].join(' ')}
						>
							<Icon name={known?.icon ?? 'sparkles'} class="size-4" />
						</span>
						<span class="min-w-0">
							<span class="flex flex-wrap items-center gap-1.5">
								<span class="text-sm font-semibold text-fg">{label(agent)}</span>
								{#if agent.required_feature}
									<Badge tone="accent" size="sm">
										{#if locked(agent)}<Icon name="lock" class="size-3" />{/if}
										{planName(unlockingTier(agent))}
									</Badge>
								{/if}
							</span>
							<span class="mt-0.5 block text-[13px] text-fg-muted">
								{known ? t(known.blurb) : agent.goal}
							</span>
						</span>
					</button>
				</li>
			{/each}
			<li class="mt-2 px-1 text-xs text-fg-subtle">
				{t('Every number comes from a tool, never from the model. Proposals change nothing.')}
			</li>
		</ul>

		{#if current && locked(current)}
			{@const tier = unlockingTier(current)}
			<div class="rounded-card border border-line bg-surface p-6 shadow-card">
				<div class="flex items-start gap-4">
					<span
						class="flex size-10 shrink-0 items-center justify-center rounded-full bg-surface-muted text-fg-muted"
					>
						<Icon name="lock" class="size-5" />
					</span>
					<div class="min-w-0">
						<p class="font-semibold text-fg">
							{t('{agent} comes with {plan}', { agent: label(current), plan: planName(tier) })}
						</p>
						<p class="mt-1 max-w-2xl text-sm text-fg-secondary">
							{t("Your current plan doesn't include this agent.")}
							{accessStore.can('manage_subscription')
								? t('Upgrade to use it with your own numbers.')
								: t('Ask the business owner to upgrade.')}
						</p>
						{#if accessStore.can('manage_subscription')}
							<Button class="mt-4" size="sm" href={`${resolve('/app/billing')}?plan=${tier}`}>
								{t('Upgrade to {plan}', { plan: planName(tier) })}
							</Button>
						{/if}
					</div>
				</div>
			</div>
		{:else if current && tenantId}
			{#key `${current.name}:${conversation}`}
				<ChatWidget
					{tenantId}
					{businessId}
					agent={current.name}
					title={label(current)}
					subtitle={presentation ? t(presentation.blurb) : current.goal}
					starters={(presentation?.starters ?? []).map((s) => t(s))}
					class="h-[calc(100dvh-14rem)] min-h-[28rem]"
				/>
			{/key}
		{/if}
	</div>
{/if}
