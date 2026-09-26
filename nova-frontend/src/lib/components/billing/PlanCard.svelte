<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * One plan in the comparison. Features are listed as what this plan adds
	 * over the one below it ("Everything in Solo, plus"), so the difference
	 * between two plans is the list itself rather than a spot-the-change.
	 * The terms that decide the bill (commission, fees, limits) sit above
	 * the features, where they are compared first.
	 */
	import Icon from '../ui/Icon.svelte';
	import Button from '../ui/Button.svelte';
	import { PLAN_COPY, featureLabel, formatPrice, planName, tierRank } from './plans.js';

	/**
	 * @type {{
	 *   plan: import('../../api/billing.js').Plan,
	 *   below?: import('../../api/billing.js').Plan|null,
	 *   annual?: boolean,
	 *   subscription?: import('../../api/billing.js').Subscription|null,
	 *   onselect?: ((plan: import('../../api/billing.js').Plan) => void)|null
	 * }}
	 */
	let { plan, below = null, annual = false, subscription = null, onselect = null } = $props();

	let copy = $derived(PLAN_COPY[plan.tier] ?? { name: plan.tier, tagline: '' });
	let free = $derived(Number(plan.monthly_price) === 0);
	let yearly = $derived(annual && plan.annual_price !== null);
	let isCurrent = $derived(subscription?.tier === plan.tier);
	let sameCycle = $derived(isCurrent && (subscription?.annual ?? false) === yearly);

	let added = $derived(
		below
			? plan.included_features.filter((f) => !below.included_features.includes(f))
			: plan.included_features
	);

	/** Months a year's price saves against twelve monthly ones. */
	let monthsFree = $derived.by(() => {
		if (!plan.annual_price) return 0;
		const monthly = Number(plan.monthly_price);
		return monthly ? Math.round((monthly * 12 - Number(plan.annual_price)) / monthly) : 0;
	});

	let terms = $derived([
		{
			label: t('New-client commission'),
			value: `${Number(plan.new_client_commission_pct)}%`
		},
		{
			label: t('Returning-client commission'),
			value: Number(plan.repeat_commission_pct)
				? `${Number(plan.repeat_commission_pct)}%`
				: t('None')
		},
		{ label: t('Online payment fee'), value: `${Number(plan.processing_fee_pct)}%` },
		{
			label: t('Team members'),
			value: plan.max_seats === null ? t('Unlimited') : String(plan.max_seats)
		},
		{
			label: t('Branches'),
			value: plan.max_locations === null ? t('Unlimited') : String(plan.max_locations)
		},
		{
			label: t('WhatsApp reminders'),
			value:
				plan.whatsapp_reminders_per_month == null
					? t('Unlimited')
					: t('{count} a month', { count: plan.whatsapp_reminders_per_month })
		}
	]);

	/** @type {{ label: string, variant: 'primary'|'outline' }|null} */
	let action = $derived.by(() => {
		if (!subscription)
			return { label: t('Start on {plan}', { plan: t(copy.name) }), variant: 'primary' };
		if (sameCycle) return null;
		if (isCurrent)
			return { label: yearly ? t('Switch to yearly') : t('Switch to monthly'), variant: 'outline' };
		return tierRank(plan.tier) > tierRank(subscription.tier)
			? { label: t('Upgrade to {plan}', { plan: t(copy.name) }), variant: 'primary' }
			: { label: t('Move to {plan}', { plan: t(copy.name) }), variant: 'outline' };
	});
</script>

<article
	class={[
		'relative flex h-full flex-col rounded-panel border bg-surface p-6 shadow-card transition-[border-color,box-shadow] duration-base',
		isCurrent
			? 'border-brand-500 ring-4 ring-brand-500/10'
			: copy.recommended
				? 'border-line-strong'
				: 'border-line'
	].join(' ')}
	aria-labelledby={`plan-${plan.tier}`}
>
	<div class="flex items-center justify-between gap-2">
		<h3 id={`plan-${plan.tier}`} class="text-lg font-semibold tracking-tight text-fg">
			{t(copy.name)}
		</h3>
		{#if isCurrent}
			<span class="rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-semibold text-accent"
				>{t('Your plan')}</span
			>
		{:else if copy.recommended}
			<span
				class="rounded-full bg-surface-muted px-2.5 py-0.5 text-xs font-semibold text-fg-secondary"
				>{t('Most popular')}</span
			>
		{/if}
	</div>
	<p class="mt-1 text-sm text-fg-muted">{copy.tagline ? t(copy.tagline) : ''}</p>

	<div class="mt-6 flex flex-wrap items-baseline gap-x-1.5">
		<p class="text-4xl font-semibold tracking-tight text-fg">
			{free
				? t('Free')
				: formatPrice(yearly ? plan.annual_price : plan.monthly_price, plan.currency)}
		</p>
		{#if !free}
			<p class="text-sm text-fg-muted">
				/ {yearly ? t('year') : t('month')}{plan.priced_per_location ? ` ${t('per branch')}` : ''}
			</p>
		{/if}
	</div>
	<p class="mt-1.5 min-h-5 text-xs text-fg-muted">
		{#if free}
			{t('No monthly fee. You pay commission only.')}
		{:else if yearly && monthsFree > 0}
			<span class="font-medium text-emerald-700 dark:text-emerald-400">
				{t('{count} months free', { count: monthsFree })}
			</span>
			{t('against paying monthly')}
		{:else if annual && plan.annual_price === null && plan.contract_months}
			{t('{count}-month contract, billed monthly', { count: plan.contract_months })}
		{:else if annual && plan.annual_price === null}
			{t('Billed monthly only')}
		{:else if plan.contract_months}
			{t('{count}-month contract', { count: plan.contract_months })}
		{:else}
			{t('Cancel any time')}
		{/if}
	</p>

	<dl class="mt-6 flex flex-col gap-2.5 border-y border-line-subtle py-5 text-sm">
		{#each terms as term (term.label)}
			<div class="flex items-baseline justify-between gap-3">
				<dt class="text-fg-muted">{term.label}</dt>
				<dd class="shrink-0 font-medium text-fg">{term.value}</dd>
			</div>
		{/each}
	</dl>

	<p class="mt-5 text-xs font-semibold tracking-wide text-fg-muted uppercase">
		{below ? t('Everything in {plan}, plus', { plan: planName(below.tier) }) : t('Includes')}
	</p>
	<ul class="mt-3 flex flex-1 flex-col gap-2.5 text-sm text-fg-secondary">
		{#each added as feature (feature)}
			<li class="flex items-start gap-2.5">
				<Icon name="check" class="mt-0.5 size-4 shrink-0 text-accent" />
				{featureLabel(feature)}
			</li>
		{/each}
	</ul>

	{#if onselect}
		<div class="mt-6">
			{#if action}
				<Button fullWidth variant={action.variant} onclick={() => onselect(plan)}>
					{action.label}
				</Button>
			{:else}
				<p
					class="flex h-10 items-center justify-center gap-2 rounded-control border border-dashed border-line-strong text-sm font-medium text-fg-muted"
				>
					<Icon name="check" class="size-4 text-accent" />
					{t('Your current plan')}
				</p>
			{/if}
		</div>
	{/if}
</article>
