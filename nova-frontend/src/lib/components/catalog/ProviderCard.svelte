<script>
	import { pickBilingual } from '../../utils/bilingual.js';
	import Avatar from '../ui/Avatar.svelte';

	/**
	 * A provider row. Selectable (a button) only when `onselect` is given;
	 * `actions` renders trailing controls, so it must not be combined with
	 * `onselect` (a button can't contain buttons).
	 *
	 * @type {{
	 *   provider: import('../../api/catalog.js').Provider,
	 *   locale?: 'en'|'ar',
	 *   selected?: boolean,
	 *   onselect?: (provider: import('../../api/catalog.js').Provider) => void,
	 *   actions?: import('svelte').Snippet
	 * }}
	 */
	let { provider, locale = 'en', selected = false, onselect, actions } = $props();

	let name = $derived(pickBilingual(provider, 'name', locale));
	let title = $derived(pickBilingual(provider, 'title', locale));

	let classes = $derived(
		[
			'flex w-full items-center gap-3 rounded-card border bg-surface p-4 text-start shadow-card',
			'transition-[border-color,box-shadow] duration-fast ease-out-premium',
			selected ? 'border-brand-500 ring-4 ring-brand-500/15' : 'border-line',
			onselect && !selected ? 'hover:border-line-strong hover:shadow-raised focus-ring' : ''
		].join(' ')
	);
</script>

{#snippet body()}
	<Avatar {name} size="md" />
	<div class="min-w-0 flex-1">
		<p class="truncate font-medium text-fg">{name}</p>
		<p class="truncate text-xs text-fg-muted">{title || 'Provider'}</p>
	</div>
	{#if actions}
		<div class="flex shrink-0 items-center gap-2">{@render actions()}</div>
	{/if}
{/snippet}

{#if onselect}
	<button type="button" class={classes} aria-pressed={selected} onclick={() => onselect(provider)}>
		{@render body()}
	</button>
{:else}
	<div class={classes}>{@render body()}</div>
{/if}
