<script>
	// Leaflet's own stylesheet. Safe to import here: it is CSS, not the library,
	// and the library itself is only ever loaded in the browser (see onMount).
	import 'leaflet/dist/leaflet.css';
	import { onMount, untrack } from 'svelte';
	import { cityCenter } from '$lib/map/cities.js';
	import { CITY_ZOOM, DEFAULT_CENTER, DEFAULT_ZOOM, PICK_ZOOM } from '$lib/map/config.js';
	import { formatCoordinates, parseCoordinates, roundCoordinate } from '$lib/map/coordinates.js';
	import { LocateError, explainFix, explainLocateError, locate } from '$lib/map/geolocate.js';
	import { addBaseLayer, loadLeaflet, pinIcon } from '$lib/map/leaflet.js';
	import Button from '$lib/components/ui/Button.svelte';
	import Input from '$lib/components/ui/Input.svelte';

	/**
	 * Where a branch is, chosen on an OpenStreetMap map with Leaflet: click the
	 * map, drag the pin, use the device's location, or type or paste coordinates.
	 * The field is not a fallback. A map is pointer-only, so the field is how a
	 * keyboard or screen-reader user places a pin at all.
	 *
	 * `latitude` and `longitude` are committed together or not at all: both are
	 * numbers, or both are null (no pin), which is the pair the API accepts
	 * (`validate_coordinates` in the catalog module). Text that is not yet a valid
	 * pair leaves them as they were and reports it through `onvalidity`, so the
	 * form that owns this can hold back its submit button.
	 *
	 * @type {{
	 *   latitude?: number | null,
	 *   longitude?: number | null,
	 *   onvalidity?: (invalid: boolean) => void,
	 *   city?: string | null,
	 *   class?: string
	 * }}
	 */
	let {
		latitude = $bindable(null),
		longitude = $bindable(null),
		onvalidity,
		city = null,
		class: className = ''
	} = $props();

	/** @type {HTMLDivElement | undefined} */
	let container = $state();
	let ready = $state(false);
	let failed = $state(false);
	let canLocate = $state(false);
	// Finding the device runs for a while, and improves as it goes.
	let finding = $state(false);
	let fixed = $state(false);
	/** @type {{ tone: 'info' | 'success' | 'warning' | 'error', text: string, detail?: string } | null} */
	let notice = $state(null);

	const noticeTone = {
		info: 'border-sky-200 bg-sky-50/70 text-sky-900 dark:border-sky-500/20 dark:bg-sky-500/10 dark:text-sky-100',
		success:
			'border-emerald-200 bg-emerald-50/70 text-emerald-900 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-100',
		warning:
			'border-amber-200 bg-amber-50/70 text-amber-900 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-100',
		error:
			'border-red-200 bg-red-50/70 text-red-900 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-100'
	};
	// The brand colour (`--color-brand-600`): Leaflet paths take a colour, not a class.
	const CIRCLE_COLOR = '#e11d48';

	// What the owner sees in the field. Separate from the committed pair so that
	// half-typed text ("24.") is not overwritten while they are still typing it.
	let text = $state(
		latitude != null && longitude != null ? formatCoordinates(latitude, longitude) : ''
	);
	let parsed = $derived(parseCoordinates(text));
	let problem = $derived(parsed.status === 'invalid' ? parsed.message : null);

	$effect(() => {
		onvalidity?.(problem !== null);
	});

	// Not reactive on purpose: nothing in the template reads them.
	/** @type {typeof import('leaflet') | undefined} */
	let L;
	/** @type {import('leaflet').Map | undefined} */
	let map;
	/** @type {import('leaflet').Marker | undefined} */
	let marker;
	/** How far off the device's fix might be, drawn round it. @type {import('leaflet').Circle | undefined} */
	let circle;
	/** The search for the device, while there is one. @type {AbortController | null} */
	let detection = null;
	/**
	 * Set when the owner typed or pasted a position, to be acted on by the next
	 * pass of the pin effect: they want to see the pin up close, to check it is on
	 * the right building. A click or a drag does not set it, because the owner is
	 * already looking at the spot they chose and the map should stay put.
	 */
	let revealPin = false;

	/** The committed pair and the field, together. @param {number} lat @param {number} lng */
	function setPin(lat, lng) {
		latitude = roundCoordinate(lat);
		longitude = roundCoordinate(lng);
		text = formatCoordinates(latitude, longitude);
	}

	function stopDetecting() {
		detection?.abort();
		detection = null;
		finding = false;
		fixed = false;
	}

	function clearCircle() {
		circle?.remove();
		circle = undefined;
	}

	/**
	 * The owner is choosing for themselves now, so whatever the device was still
	 * working out is no longer wanted. A late fix must never move a pin they placed.
	 */
	function takeOver() {
		stopDetecting();
		clearCircle();
		notice = null;
	}

	/** The owner puts the pin somewhere. @param {number} lat @param {number} lng */
	function place(lat, lng) {
		takeOver();
		setPin(lat, lng);
	}

	function removePin() {
		takeOver();
		latitude = null;
		longitude = null;
		text = '';
	}

	/** @param {Event & { currentTarget: HTMLInputElement }} event */
	function handleInput(event) {
		takeOver();
		text = event.currentTarget.value;
		const next = parseCoordinates(text);
		if (next.status === 'ok') {
			revealPin = true;
			latitude = next.latitude;
			longitude = next.longitude;
		} else if (next.status === 'empty') {
			latitude = null;
			longitude = null;
		}
		// 'invalid': keep the last good pair, and let `onvalidity` say so.
	}

	/**
	 * A fix from the device. Draws how far off it might be, and puts the pin there
	 * only if it is accurate enough to trust with one.
	 * @param {import('$lib/map/geolocate.js').Fix} fix
	 */
	function applyFix(fix) {
		// The owner took over, or cancelled, while this was on its way.
		if (!detection) return;
		fixed = true;
		const outcome = explainFix(fix);
		notice = { tone: outcome.tone, text: outcome.text };
		if (outcome.pin) setPin(fix.latitude, fix.longitude);

		if (!map || !L) return;
		if (circle) circle.setLatLng([fix.latitude, fix.longitude]).setRadius(fix.accuracy);
		else {
			circle = L.circle([fix.latitude, fix.longitude], {
				radius: fix.accuracy,
				color: CIRCLE_COLOR,
				weight: 1,
				fillColor: CIRCLE_COLOR,
				fillOpacity: 0.12,
				// Clicks go through to the map, so the owner can still place a pin.
				interactive: false
			}).addTo(map);
		}
		// Frame what was found. A precise fix is a dot, so this zooms right in; a
		// rough one is a wide circle, so it stays out far enough to show it whole.
		map.fitBounds(circle.getBounds(), {
			maxZoom: outcome.pin ? PICK_ZOOM : 13,
			padding: [24, 24],
			animate: false
		});
	}

	async function useMyLocation() {
		takeOver();
		const controller = new AbortController();
		detection = controller;
		finding = true;
		notice = {
			tone: 'info',
			text: 'Finding your location. On a computer this can take up to half a minute.'
		};
		try {
			await locate({ signal: controller.signal, onfix: applyFix });
		} catch (error) {
			if (detection !== controller) return; // the owner took over
			const failure = error instanceof LocateError ? error : new LocateError('unavailable');
			const ua = navigator.userAgent;
			notice = {
				tone: 'error',
				text: explainLocateError(failure, {
					origin: window.location.origin,
					linux: /linux/i.test(ua) && !/android/i.test(ua)
				}),
				// What the browser itself said, for the owner and for whoever they ask.
				detail: failure.detail || undefined
			};
		} finally {
			if (detection === controller) {
				detection = null;
				finding = false;
				fixed = false;
			}
		}
	}

	/** Stop searching, but keep whatever has been found so far. */
	function cancelDetecting() {
		stopDetecting();
		if (!circle) notice = null;
	}

	onMount(() => {
		canLocate = 'geolocation' in navigator;
		let disposed = false;
		/** @type {ResizeObserver | undefined} */
		let observer;

		(async () => {
			try {
				const leaflet = await loadLeaflet();
				if (disposed || !container) return;
				L = leaflet;

				const start = latitude != null && longitude != null;
				map = L.map(container, {
					center: start ? [latitude ?? 0, longitude ?? 0] : DEFAULT_CENTER,
					zoom: start ? PICK_ZOOM : DEFAULT_ZOOM,
					// This sits in a modal that scrolls. Wheel-zoom is off until the
					// map is clicked, so scrolling the form does not get trapped.
					scrollWheelZoom: false
				});
				addBaseLayer(L, map);

				map.on('click', (event) => {
					const at = event.latlng.wrap();
					place(at.lat, at.lng);
					map?.scrollWheelZoom.enable();
				});
				map.on('mouseout', () => map?.scrollWheelZoom.disable());

				observer = new ResizeObserver(() => map?.invalidateSize());
				observer.observe(container);

				ready = true;
			} catch {
				failed = true;
			}
		})();

		return () => {
			disposed = true;
			detection?.abort();
			detection = null;
			observer?.disconnect();
			map?.remove();
			map = undefined;
			marker = undefined;
			circle = undefined;
			ready = false;
		};
	});

	// The pin follows the committed pair, whoever changed it: a click, a drag, the
	// field, the device's location, or the form that owns this resetting it.
	$effect(() => {
		if (!ready || !map || !L) return;
		const lat = latitude;
		const lng = longitude;

		if (lat == null || lng == null) {
			marker?.remove();
			marker = undefined;
			return;
		}

		// Read after the `ready` check above, so a position typed before the map had
		// loaded is still revealed once it has.
		const reveal = revealPin;
		revealPin = false;

		/** @type {import('leaflet').LatLngTuple} */
		const at = [lat, lng];
		if (!marker) {
			const dropped = L.marker(at, {
				icon: pinIcon(L),
				draggable: true,
				// Leaflet sets this as a property, not markup.
				title: 'Branch position. Drag to move it.'
			}).addTo(map);
			dropped.on('dragend', () => {
				const moved = dropped.getLatLng().wrap();
				place(moved.lat, moved.lng);
			});
			marker = dropped;
		} else if (!marker.getLatLng().equals(at)) {
			marker.setLatLng(at);
		}
		if (reveal) {
			// Never zoom *out* from a view they have already closed in on.
			map.setView(at, Math.max(map.getZoom(), PICK_ZOOM), { animate: false });
		} else if (!map.getBounds().contains(at)) {
			// Set from somewhere else (a reset, say) and off screen.
			map.setView(at, PICK_ZOOM, { animate: false });
		}
	});

	// The form's committed pair changed from outside (a reset): the field follows.
	// `text` is read untracked, or this would rewrite half-typed text on every
	// keystroke.
	$effect(() => {
		const lat = latitude;
		const lng = longitude;
		const current = untrack(() => parseCoordinates(text));
		if (lat == null || lng == null) {
			if (current.status === 'ok') text = '';
			return;
		}
		const same =
			current.status === 'ok' &&
			Math.abs(current.latitude - lat) < 1e-9 &&
			Math.abs(current.longitude - lng) < 1e-9;
		if (!same) text = formatCoordinates(lat, lng);
	});

	// Typing a city moves the map there, so placing a pin starts in the right
	// district. Only while there is no pin: an owner who has already placed one
	// does not want the view pulled away from it.
	$effect(() => {
		if (!ready || !map) return;
		const centre = cityCenter(city);
		if (centre && untrack(() => latitude == null)) {
			map.setView(centre, CITY_ZOOM, { animate: false });
		}
	});
</script>

<div class={['flex flex-col gap-2', className]}>
	<div class="flex items-baseline justify-between gap-2">
		<span class="text-sm font-medium text-fg-secondary">Map position</span>
		<span class="text-xs text-fg-muted">Optional</span>
	</div>

	<!-- `isolate` keeps Leaflet's z-indexes (up to 1000) from escaping this box. -->
	<div
		class="relative isolate h-64 overflow-hidden rounded-card border border-line-strong bg-surface-muted shadow-card"
	>
		<div
			bind:this={container}
			class="absolute inset-0"
			role="region"
			aria-label="Map for placing the branch pin. Click it to place the pin, or type coordinates below."
		></div>
		{#if failed}
			<div class="absolute inset-0 flex items-center justify-center p-6 text-center">
				<p class="text-sm text-fg-muted">
					The map could not be loaded. You can still type coordinates below.
				</p>
			</div>
		{/if}
	</div>

	<div class="flex flex-wrap items-center gap-2">
		{#if canLocate}
			<Button variant="outline" size="sm" onclick={useMyLocation} disabled={finding}>
				{finding ? 'Finding your location…' : 'Use my location'}
			</Button>
			{#if finding}
				<Button variant="ghost" size="sm" onclick={cancelDetecting}>Cancel</Button>
			{/if}
		{/if}
		{#if latitude != null && longitude != null}
			<Button variant="ghost" size="sm" onclick={removePin}>Remove pin</Button>
		{/if}
	</div>
	{#if notice}
		<div
			role="status"
			class={['rounded-control border px-3 py-2 text-sm', noticeTone[notice.tone]]}
		>
			<p>
				{notice.text}{#if finding && fixed}<span class="ms-1">Refining…</span>{/if}
			</p>
			{#if notice.detail}
				<p class="mt-1 text-xs opacity-75">Your browser said: {notice.detail}</p>
			{/if}
		</div>
	{/if}

	<Input
		label="Coordinates"
		placeholder="24.7136, 46.6753"
		value={text}
		oninput={handleInput}
		error={problem}
		hint="Click the map, drag the pin, or paste coordinates. A branch without a pin does not appear on the map when customers browse."
	/>
</div>
