<script>
	import { t } from '$lib/i18n/index.svelte.js';
	import { pickBilingual } from '../../utils/bilingual.js';
	import Badge from '../ui/Badge.svelte';
	import Button from '../ui/Button.svelte';
	import Card from '../ui/Card.svelte';
	import Icon from '../ui/Icon.svelte';

	/**
	 * `onsetposition`, `onedit` and `ondelete` are what make the card
	 * interactive; a card shown read-only simply omits them.
	 * @type {{
	 *   location: import('../../api/catalog.js').Location,
	 *   onsetposition?: (location: import('../../api/catalog.js').Location) => void,
	 *   onedit?: (location: import('../../api/catalog.js').Location) => void,
	 *   ondelete?: (location: import('../../api/catalog.js').Location) => void
	 * }}
	 */
	let { location, onsetposition, onedit, ondelete } = $props();

	// A branch is on the marketplace map only if it has both coordinates.
	let pinned = $derived(location.latitude != null && location.longitude != null);

	// OpenStreetMap's own permalink, with a marker on the point. Both numbers come
	// from the API as floats and are formatted here, never concatenated raw.
	let openStreetMapUrl = $derived(
		pinned
			? `https://www.openstreetmap.org/?mlat=${Number(location.latitude).toFixed(6)}&mlon=${Number(location.longitude).toFixed(6)}#map=17/${Number(location.latitude).toFixed(6)}/${Number(location.longitude).toFixed(6)}`
			: null
	);
</script>

<Card padding="none" class="flex flex-col">
	<div class="flex items-start gap-3 p-4">
		<span
			class="flex size-10 shrink-0 items-center justify-center rounded-control bg-accent-soft text-accent"
		>
			<Icon name="building" class="size-5" />
		</span>
		<div class="min-w-0 flex-1">
			<p class="flex items-center gap-2 font-semibold text-fg">
				<span class="truncate">{pickBilingual(location, 'name')}</span>
				{#if !location.is_active}<Badge size="sm">{t('Inactive')}</Badge>{/if}
			</p>
			{#if location.city}
				<p class="mt-0.5 truncate text-sm text-fg-muted">{t(location.city)}</p>
			{/if}
			<p class="mt-0.5 text-xs text-fg-subtle">{location.timezone}</p>
		</div>
		{#if onedit || ondelete}
			<div class="flex shrink-0 items-center gap-1">
				{#if onedit}
					<Button size="sm" variant="ghost" onclick={() => onedit(location)}>{t('Edit')}</Button>
				{/if}
				{#if ondelete}
					<Button size="sm" variant="danger-ghost" onclick={() => ondelete(location)}>
						{t('Delete')}
					</Button>
				{/if}
			</div>
		{/if}
	</div>

	<div
		class="mt-auto flex flex-wrap items-center justify-between gap-2 rounded-b-card border-t border-line-subtle bg-surface-sunken px-4 py-3"
	>
		<div class="flex flex-wrap items-center gap-2.5 text-xs">
			{#if pinned}
				<Badge tone="success" size="sm">
					<Icon name="map-pin" class="size-3" />
					{t('On the map')}
				</Badge>
				<!-- An external, absolute URL built above, not an app route, so it does not
				     go through SvelteKit's resolve(). -->
				<!-- eslint-disable svelte/no-navigation-without-resolve -->
				<a
					href={openStreetMapUrl}
					target="_blank"
					rel="noopener noreferrer"
					class="inline-flex items-center gap-0.5 font-medium text-accent hover:underline"
				>
					{t('View on OpenStreetMap')}<span class="sr-only"> {t('(opens in a new tab)')}</span>
					<Icon name="arrow-up-right" class="size-3" />
				</a>
				<!-- eslint-enable svelte/no-navigation-without-resolve -->
			{:else}
				<Badge tone="warning" size="sm" dot>{t('Not on the map yet')}</Badge>
			{/if}
		</div>
		{#if onsetposition}
			<Button variant="outline" size="sm" onclick={() => onsetposition(location)}>
				{pinned ? t('Move pin') : t('Set on map')}
			</Button>
		{/if}
	</div>
</Card>
