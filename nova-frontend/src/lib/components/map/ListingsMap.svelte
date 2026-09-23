<script>
	// Leaflet's own stylesheet. Safe to import here: it is CSS, not the library,
	// and the library itself is only ever loaded in the browser (see onMount).
	import 'leaflet/dist/leaflet.css';
	import { onMount, untrack } from 'svelte';
	import { pickBilingual } from '$lib/utils/bilingual.js';
	import { toBBox } from '$lib/map/bbox.js';
	import { DEFAULT_CENTER, DEFAULT_ZOOM, FIT_MAX_ZOOM } from '$lib/map/config.js';
	import { addBaseLayer, hereIcon, loadLeaflet, pinIcon } from '$lib/map/leaflet.js';
	import Icon from '$lib/components/ui/Icon.svelte';

	/**
	 * Branches drawn on an OpenStreetMap map with Leaflet. Presentational: it
	 * owns the map, and hands every decision back — which pin was picked, which
	 * area was asked for — through callbacks.
	 *
	 * @type {{
	 *   listings: import('$lib/api/discovery.js').ListingCard[],
	 *   fit?: boolean,
	 *   loading?: boolean,
	 *   truncated?: boolean,
	 *   areaActive?: boolean,
	 *   onselect?: (listing: import('$lib/api/discovery.js').ListingCard) => void,
	 *   onsearcharea?: (bbox: string) => void,
	 *   onclear?: () => void,
	 *   here?: { latitude: number, longitude: number, accuracy: number } | null,
	 *   onmovehere?: (position: { latitude: number, longitude: number }) => void,
	 *   class?: string
	 * }}
	 */
	let {
		listings,
		fit = true,
		loading = false,
		truncated = false,
		areaActive = false,
		onselect,
		onsearcharea,
		onclear,
		here = null,
		onmovehere,
		class: className = ''
	} = $props();

	/** @type {HTMLDivElement | undefined} */
	let container = $state();
	let ready = $state(false);
	let failed = $state(false);

	// Not reactive on purpose: nothing in the template reads them.
	/** @type {typeof import('leaflet') | undefined} */
	let L;
	/** @type {import('leaflet').Map | undefined} */
	let map;
	/** @type {import('leaflet').LayerGroup | undefined} */
	let pins;
	/** The customer's position and its accuracy circle. */
	/** @type {import('leaflet').LayerGroup | undefined} */
	let hereLayer;
	/** Where the map last centred on `here`, so it recentres only when that moves. */
	/** @type {{ latitude: number, longitude: number } | null} */
	let centredOn = null;
	/**
	 * A fit asked for while the map had no size (its tab was hidden), to be done
	 * the moment it has one. Fitting a zero-sized map picks a meaningless zoom.
	 * @type {import('leaflet').LatLngBounds | null}
	 */
	let pendingFit = null;

	onMount(() => {
		let disposed = false;
		/** @type {ResizeObserver | undefined} */
		let observer;

		(async () => {
			try {
				const leaflet = await loadLeaflet();
				if (disposed || !container) return;
				L = leaflet;

				map = L.map(container, {
					center: DEFAULT_CENTER,
					zoom: DEFAULT_ZOOM,
					// The map sits in a scrolling page. Wheel-zoom is off until the
					// map is clicked, so scrolling past it does not get trapped.
					scrollWheelZoom: false
				});
				addBaseLayer(L, map);
				pins = L.layerGroup().addTo(map);
				hereLayer = L.layerGroup().addTo(map);

				map.on('click', () => map?.scrollWheelZoom.enable());
				map.on('mouseout', () => map?.scrollWheelZoom.disable());

				// The container changes size without the window doing so: a mobile
				// customer flips from the list to the map and it goes from display:
				// none to visible. Leaflet only watches the window.
				observer = new ResizeObserver(() => {
					if (!map) return;
					map.invalidateSize();
					if (pendingFit && container && container.clientWidth > 0) {
						map.fitBounds(pendingFit, { padding: [40, 40], maxZoom: FIT_MAX_ZOOM });
						pendingFit = null;
					}
				});
				observer.observe(container);

				ready = true;
			} catch {
				failed = true;
			}
		})();

		return () => {
			disposed = true;
			observer?.disconnect();
			map?.remove();
			map = undefined;
			pins = undefined;
			hereLayer = undefined;
			centredOn = null;
			ready = false;
		};
	});

	// Redraw the pins whenever the listings change.
	$effect(() => {
		if (!ready || !map || !pins || !L) return;
		const items = listings;
		const shouldFit = untrack(() => fit);

		pins.clearLayers();
		/** @type {import('leaflet').LatLngTuple[]} */
		const points = [];
		for (const listing of items) {
			if (listing.latitude == null || listing.longitude == null) continue;
			/** @type {import('leaflet').LatLngTuple} */
			const point = [listing.latitude, listing.longitude];
			points.push(point);
			L.marker(point, {
				icon: pinIcon(L),
				// Leaflet sets this as a property, not markup, and it becomes the
				// pin's accessible name: the pin is a keyboard-focusable button.
				title: `${pickBilingual(listing, 'name', 'en')} — ${listing.location_name_en}`,
				riseOnHover: true
			})
				.on('click', () => onselect?.(listing))
				.addTo(pins);
		}

		// Fitting to every pin would zoom out past the customer; when we know
		// where they are, the map stays on them (see the effect below).
		if (shouldFit && points.length > 0 && !untrack(() => here)) {
			const bounds = L.latLngBounds(points);
			if (container && container.clientWidth > 0) {
				map.fitBounds(bounds, { padding: [40, 40], maxZoom: FIT_MAX_ZOOM });
			} else {
				pendingFit = bounds;
			}
		}
	});

	// The customer's position: an accuracy circle (how sure the browser is) and
	// a dot they can drag to where they really are.
	$effect(() => {
		if (!ready || !map || !hereLayer || !L) return;
		const position = here;
		hereLayer.clearLayers();
		if (!position) {
			centredOn = null;
			return;
		}
		const point = /** @type {import('leaflet').LatLngTuple} */ ([
			position.latitude,
			position.longitude
		]);
		if (position.accuracy > 0) {
			L.circle(point, {
				radius: position.accuracy,
				color: '#0ea5e9',
				weight: 1,
				fillColor: '#0ea5e9',
				fillOpacity: 0.1,
				interactive: false
			}).addTo(hereLayer);
		}
		const marker = L.marker(point, {
			icon: hereIcon(L),
			draggable: Boolean(onmovehere),
			keyboard: true,
			title: 'You are here — drag to correct',
			zIndexOffset: 1000
		}).addTo(hereLayer);
		marker.on('dragend', () => {
			const moved = marker.getLatLng();
			onmovehere?.({ latitude: moved.lat, longitude: moved.lng });
		});

		// Recentre when the position itself moves, not when only its accuracy
		// improves, and never after the customer placed it by hand (they are
		// looking at the map already).
		const moved =
			!centredOn ||
			Math.abs(centredOn.latitude - position.latitude) > 1e-4 ||
			Math.abs(centredOn.longitude - position.longitude) > 1e-4;
		if (moved && position.accuracy > 0) {
			if (position.accuracy <= 2000) map.setView(point, Math.max(map.getZoom(), 14));
			else map.fitBounds(L.latLng(point).toBounds(position.accuracy * 2), { maxZoom: 14 });
		}
		centredOn = { latitude: position.latitude, longitude: position.longitude };
	});

	function searchThisArea() {
		if (map) onsearcharea?.(toBBox(map.getBounds()));
	}

	const overlayButton =
		'pointer-events-auto inline-flex h-9 items-center gap-1.5 rounded-full border border-line bg-surface px-4 text-xs font-semibold text-fg shadow-raised transition-colors duration-fast hover:bg-surface-muted focus-ring disabled:opacity-50';
	const overlayNote =
		'rounded-control border border-line bg-surface/95 px-3 py-1.5 text-[11px] font-medium text-fg-secondary shadow-raised backdrop-blur';
</script>

<!-- `isolate` gives the map its own stacking context. Leaflet's panes and
     controls use z-indexes from 200 up to 1000, which would otherwise paint
     over the Quick View modal and anything else on the page below that. From
     `lg` up the sticky wrapper around the map is a stacking context already,
     so this matters on smaller screens, where nothing else contains it. -->
<div
	class={[
		'relative isolate overflow-hidden rounded-panel border border-line bg-surface-muted shadow-card',
		className
	]}
>
	<div
		bind:this={container}
		class="absolute inset-0"
		role="region"
		aria-label="Map of salons and spas"
	></div>

	{#if failed}
		<div class="absolute inset-0 flex items-center justify-center p-6 text-center">
			<p class="text-sm text-fg-muted">
				The map could not be loaded. The list still shows every result.
			</p>
		</div>
	{:else}
		<div class="pointer-events-none absolute inset-x-0 top-3 z-[1000] flex justify-center">
			{#if areaActive}
				<button type="button" class={overlayButton} onclick={() => onclear?.()}>
					<Icon name="x" class="size-3.5" />
					Clear area
				</button>
			{:else}
				<button type="button" class={overlayButton} onclick={searchThisArea} disabled={!ready}>
					<Icon name="search" class="size-3.5" />
					Search this area
				</button>
			{/if}
		</div>

		<div class="pointer-events-none absolute start-3 bottom-8 z-[1000] max-w-[70%]">
			{#if truncated}
				<p class={overlayNote}>
					Showing the first {listings.length} branches. Zoom in and search an area to see more.
				</p>
			{:else if ready && !loading && listings.length === 0}
				<p class={overlayNote}>No branches with a location match this search.</p>
			{/if}
		</div>
	{/if}
</div>
