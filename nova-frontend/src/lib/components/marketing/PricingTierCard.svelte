<script>
	import { formatMoney } from '$lib/utils/money.js';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import GradientBlob from './GradientBlob.svelte';

	/**
	 * Static marketing pricing tier. Not wired to the billing API — the real
	 * plan/subscription data lives behind auth in /app/billing
	 * (`$lib/api/billing.js`); this is illustrative pricing copy only.
	 *
	 * @type {{
	 *   name: string,
	 *   priceMonthly: number,
	 *   currency?: string,
	 *   description: string,
	 *   features: string[],
	 *   featured?: boolean,
	 *   ctaLabel?: string,
	 *   ctaHref: string
	 * }}
	 */
	let {
		name,
		priceMonthly,
		currency = 'SAR',
		description,
		features,
		featured = false,
		ctaLabel = 'Get started',
		ctaHref
	} = $props();
</script>

<div
	class={[
		'relative flex flex-col overflow-hidden rounded-2xl border p-8',
		featured
			? 'border-brand-300 bg-white shadow-xl ring-2 ring-brand-500 dark:border-brand-700 dark:bg-slate-900'
			: 'border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900'
	].join(' ')}
>
	{#if featured}
		<GradientBlob variant="corner" />
		<div class="absolute end-4 top-4">
			<Badge tone="accent">Most popular</Badge>
		</div>
	{/if}

	<h3 class="text-lg font-semibold text-slate-900 dark:text-slate-100">{name}</h3>
	<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">{description}</p>

	<p class="mt-6 flex items-baseline gap-1">
		<span class="text-display-md font-semibold tracking-tight text-slate-900 dark:text-slate-100">
			{formatMoney(priceMonthly, currency, 'en')}
		</span>
		<span class="text-sm text-slate-500 dark:text-slate-400">/month</span>
	</p>

	<ul class="mt-6 flex-1 space-y-3">
		{#each features as feature (feature)}
			<li class="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-300">
				<Icon name="check" class="mt-0.5 size-4 shrink-0 text-brand-600 dark:text-brand-400" />
				<span>{feature}</span>
			</li>
		{/each}
	</ul>

	<Button href={ctaHref} variant={featured ? 'primary' : 'outline'} class="mt-8" fullWidth>
		{ctaLabel}
	</Button>
</div>
