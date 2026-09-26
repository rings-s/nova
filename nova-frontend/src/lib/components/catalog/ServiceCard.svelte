<script>
	import { minutesLabel } from '$lib/i18n/labels.js';
	import { pickBilingual } from '../../utils/bilingual.js';
	import { formatMoney } from '../../utils/money.js';
	import { t } from '$lib/i18n/index.svelte.js';
	import Badge from '../ui/Badge.svelte';
	import Icon from '../ui/Icon.svelte';

	/**
	 * Renders either a tenant-side `Service` (catalog.js) or a public
	 * `StorefrontService` (discovery.js) — the two share every field this uses.
	 * Selectable (a button) only when `onselect` is given. `actions` renders
	 * trailing controls, so it must not be combined with `onselect` (a button
	 * can't contain buttons).
	 *
	 * @type {{
	 *   service: import('../../api/catalog.js').Service|import('../../api/discovery.js').StorefrontService,
	 *   selected?: boolean,
	 *   onselect?: (service: import('../../api/catalog.js').Service|import('../../api/discovery.js').StorefrontService) => void,
	 *   actions?: import('svelte').Snippet
	 * }}
	 */
	let { service, selected = false, onselect, actions } = $props();

	// Only the dashboard's `Service` carries it; a storefront shows active ones only.
	let inactive = $derived('is_active' in service && !service.is_active);

	let description = $derived(pickBilingual(service, 'description'));

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
					{pickBilingual(service.category, 'name')}
				</p>
			{/if}
			<p class="font-semibold text-fg">{pickBilingual(service, 'name')}</p>
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
			{minutesLabel(service.duration_minutes)}
		</span>
		<span class="text-sm font-semibold text-fg tabular-nums">
			{formatMoney(service.price, service.currency)}
		</span>
	</div>
	{#if inactive || actions}
		<div class="mt-3 flex items-center justify-between gap-2 border-t border-line-subtle pt-3">
			<span
				>{#if inactive}<Badge size="sm">{t('Inactive')}</Badge>{/if}</span
			>
			{#if actions}<div class="flex items-center gap-1">{@render actions()}</div>{/if}
		</div>
	{/if}
{/snippet}

{#if onselect}
	<button type="button" class={classes} aria-pressed={selected} onclick={() => onselect(service)}>
		{@render body()}
	</button>
{:else}
	<div class={classes}>{@render body()}</div>
{/if}
