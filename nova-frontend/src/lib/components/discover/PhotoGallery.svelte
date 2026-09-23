<script>
	/**
	 * A storefront's photos: a mosaic (the cover large, up to four more beside
	 * it) and a full-screen viewer for all of them. The viewer takes the arrow
	 * keys and Escape, and returns focus to whatever opened it.
	 */
	import { apiAssetUrl } from '../../api/client.js';
	import Icon from '../ui/Icon.svelte';

	/** @type {{ photos: import('../../api/discovery.js').PublicPhoto[], name: string }} */
	let { photos, name } = $props();

	let open = $state(false);
	let index = $state(0);
	/** @type {HTMLElement|null} */
	let returnFocus = null;
	/** @type {HTMLButtonElement|undefined} */
	let closeButton = $state();

	let shown = $derived(photos.slice(0, 5));
	let current = $derived(photos[index]);

	/** @param {number} at @param {Event} event */
	function view(at, event) {
		returnFocus = /** @type {HTMLElement} */ (event.currentTarget);
		index = at;
		open = true;
		queueMicrotask(() => closeButton?.focus());
	}

	function close() {
		open = false;
		returnFocus?.focus();
	}

	/** @param {number} step */
	function move(step) {
		index = (index + step + photos.length) % photos.length;
	}

	/** @param {KeyboardEvent} event */
	function onkeydown(event) {
		if (!open) return;
		if (event.key === 'Escape') close();
		const rtl = document.documentElement.dir === 'rtl';
		if (event.key === 'ArrowRight') move(rtl ? -1 : 1);
		if (event.key === 'ArrowLeft') move(rtl ? 1 : -1);
	}

	$effect(() => {
		if (!open) return;
		const previous = document.body.style.overflow;
		document.body.style.overflow = 'hidden';
		return () => {
			document.body.style.overflow = previous;
		};
	});
</script>

<svelte:window {onkeydown} />

{#if photos.length > 0}
	<div
		class={[
			'relative grid gap-2 overflow-hidden rounded-panel',
			shown.length === 1 ? 'grid-cols-1' : 'grid-cols-4 grid-rows-2',
			'h-56 sm:h-80 lg:h-96'
		].join(' ')}
	>
		{#each shown as photo, i (photo.id)}
			<button
				type="button"
				onclick={(e) => view(i, e)}
				class={[
					'group relative overflow-hidden bg-surface-muted focus-ring',
					shown.length === 1
						? ''
						: i === 0
							? 'col-span-4 row-span-2 sm:col-span-2'
							: 'hidden sm:block',
					shown.length === 2 && i === 1 ? 'sm:col-span-2 sm:row-span-2' : ''
				].join(' ')}
				aria-label={`View photo ${i + 1} of ${photos.length}`}
			>
				<img
					src={apiAssetUrl(i === 0 ? photo.urls.large : photo.urls.thumb)}
					alt={i === 0 ? `${name}` : ''}
					loading={i === 0 ? 'eager' : 'lazy'}
					class="duration-slow size-full object-cover transition-transform ease-out-premium group-hover:scale-[1.03]"
				/>
			</button>
		{/each}
		{#if photos.length > 1}
			<button
				type="button"
				onclick={(e) => view(0, e)}
				class="absolute end-3 bottom-3 inline-flex h-9 items-center gap-2 rounded-control border border-line bg-surface/90 px-3 text-sm font-medium text-fg shadow-raised focus-ring backdrop-blur transition-colors hover:bg-surface"
			>
				<Icon name="layers" class="size-4" />
				Show all {photos.length} photos
			</button>
		{/if}
	</div>
{/if}

{#if open && current}
	<div
		class="fixed inset-0 z-50 flex animate-fade-in flex-col bg-slate-950/95"
		role="dialog"
		aria-modal="true"
		aria-label={`${name} photos`}
	>
		<div class="flex items-center justify-between px-4 py-3 text-white sm:px-6">
			<p class="text-sm tabular-nums" aria-live="polite">{index + 1} / {photos.length}</p>
			<button
				bind:this={closeButton}
				type="button"
				onclick={close}
				class="flex size-10 items-center justify-center rounded-full text-white/80 focus-ring hover:bg-white/10 hover:text-white"
				aria-label="Close photos"
			>
				<Icon name="x" class="size-6" />
			</button>
		</div>
		<div class="relative flex min-h-0 flex-1 items-center justify-center px-4 pb-6 sm:px-16">
			<img
				src={apiAssetUrl(current.urls.large)}
				alt={`${name} — photo ${index + 1}`}
				class="max-h-full max-w-full rounded-card object-contain"
			/>
			{#if photos.length > 1}
				<button
					type="button"
					onclick={() => move(-1)}
					class="absolute start-2 top-1/2 flex size-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 text-white focus-ring hover:bg-white/20 sm:start-4"
					aria-label="Previous photo"
				>
					<Icon name="chevron-left" class="size-6 rtl:rotate-180" />
				</button>
				<button
					type="button"
					onclick={() => move(1)}
					class="absolute end-2 top-1/2 flex size-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 text-white focus-ring hover:bg-white/20 sm:end-4"
					aria-label="Next photo"
				>
					<Icon name="chevron-right" class="size-6 rtl:rotate-180" />
				</button>
			{/if}
		</div>
	</div>
{/if}
