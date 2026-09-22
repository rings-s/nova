<script>
	import { pickBilingual } from '../../utils/bilingual.js';
	import { formatMoney } from '../../utils/money.js';
	import Icon from '../ui/Icon.svelte';

	/**
	 * Renders either a tenant-side `Service` (catalog.js) or a public
	 * `StorefrontService` (discovery.js) — the two share every field this uses.
	 * Selectable (a button) only when `onselect` is given.
	 *
	 * @type {{
	 *   service: import('../../api/catalog.js').Service|import('../../api/discovery.js').StorefrontService,
	 *   locale?: 'en'|'ar',
	 *   selected?: boolean,
	 *   onselect?: (service: import('../../api/catalog.js').Service|import('../../api/discovery.js').StorefrontService) => void
	 * }}
	 */
	let { service, locale = 'en', selected = false, onselect } = $props();

	let description = $derived(pickBilingual(service, 'description', locale));

	let classes = $derived(
		[
			'flex h-full w-full flex-col rounded-card border bg-surface p-4 text-start shadow-card',
			'transition-[border-color,box-shadow] duration-fast ease-out-premium',
			selected ? 'border-brand-500 ring-4 ring-brand-500/15' : 'border-line',
			onselect && !selected ? 'hover:border-line-strong hover:shadow-raised focus-ring' : ''
		].join(' ')
	);
</script>

{#snippet body()}
	<div class="flex items-start justify-between gap-3">
		<div class="min-w-0">
			{#if service.category}
				<p class="mb-0.5 text-[11px] font-semibold tracking-wider text-fg-subtle uppercase">
					{service.category}
				</p>
			{/if}
			<p class="font-semibold text-fg">{pickBilingual(service, 'name', locale)}</p>
		</div>
		{#if selected}
			<span
				class="flex size-5 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white"
			>
				<Icon name="check" class="size-3.5" />
			</span>
		{/if}
	</div>
	{#if description}
		<p class="mt-1.5 line-clamp-2 text-sm text-fg-muted">{description}</p>
	{/if}
	<div class="mt-auto flex items-center justify-between gap-3 pt-4">
		<span class="inline-flex items-center gap-1.5 text-xs text-fg-muted">
			<Icon name="clock" class="size-3.5" />
			{service.duration_minutes} min
		</span>
		<span class="text-sm font-semibold text-fg tabular-nums">
			{formatMoney(service.price, service.currency, locale)}
		</span>
	</div>
{/snippet}

{#if onselect}
	<button type="button" class={classes} aria-pressed={selected} onclick={() => onselect(service)}>
		{@render body()}
	</button>
{:else}
	<div class={classes}>{@render body()}</div>
{/if}
