<script>
	import { t, tp, m, i18n } from '$lib/i18n/index.svelte.js';
	import { listCategories, mapBusinesses, searchBusinesses } from '$lib/api/discovery.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { pickBilingual } from '$lib/utils/bilingual.js';
	import { formatMoney } from '$lib/utils/money.js';
	import { resolve } from '$app/paths';
	import { SvelteSet } from 'svelte/reactivity';
	import { tick } from 'svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';
	import ListingsMap from '$lib/components/map/ListingsMap.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import { fieldBase, fieldBorder } from '$lib/components/ui/styles.js';
	import RatingStars from '$lib/components/review/RatingStars.svelte';
	import { apiAssetUrl } from '$lib/api/client.js';
	import { describeAccuracy, locate, LocateError, metresBetween } from '$lib/map/geolocate.js';
	import AssistantLauncher from '$lib/components/ai/AssistantLauncher.svelte';

	/** What is in the search box. */
	let q = $state('');
	/**
	 * What is searched: the box, once typing pauses (or on Enter). The list and
	 * the map share one 60-requests-a-minute allowance per address, so a search
	 * per keystroke would spend it in a sentence.
	 */
	let term = $state('');
	let selectedCategory = $state('');
	let sortBy = $state('recommended');
	let offset = $state(0);
	const limit = 12;

	let loading = $state(true);
	let listings = $state(/** @type {any[]} */ ([]));
	let hasNextPage = $state(false);
	let searchTicket = 0;

	// The map runs the same search as the list, but unpaged, so its pins cover
	// every match and not only the twelve cards on screen.
	let pins = $state(/** @type {import('$lib/api/discovery.js').ListingCard[]} */ ([]));
	let pinsLoading = $state(true);
	let pinsTruncated = $state(false);
	/**
	 * A viewport the customer chose with "Search this area", as
	 * `west,south,east,north`. Null searches everywhere.
	 */
	let area = $state(/** @type {string | null} */ (null));
	// The list and the map take turns on the screen at every width: the map is a
	// view of the results, not a panel squeezed in beside them.
	const views = /** @type {const} */ ([
		{ id: 'list', label: m('List'), icon: 'list' },
		{ id: 'map', label: m('Map'), icon: 'map' }
	]);
	let view = $state(/** @type {'list' | 'map'} */ ('list'));

	/** Top of the results, scrolled to when the page or the view changes. */
	/** @type {HTMLElement | undefined} */
	let resultsTop = $state();
	/** @type {HTMLElement | undefined} */
	let mapBox = $state();

	/** Covers whose image failed to load, drawn as the initial on the gradient instead. */
	const brokenCovers = new SvelteSet();

	// Quick View Modal
	let quickViewSalon = $state(/** @type {any | null} */ (null));

	// Not a filter: registers the city names that a card's badge translates with `t(listing.city)`.
	m('Riyadh');
	m('Jeddah');
	m('Al Khobar');

	let serviceCategories = $state(/** @type {import('$lib/api/catalog.js').Category[]} */ ([]));
	let categories = $derived([
		{ id: '', name: t('All Services'), icon: /** @type {const} */ ('sparkles') },
		...serviceCategories.map((category) => ({
			id: category.slug,
			name: pickBilingual(category, 'name'),
			icon:
				category.slug === 'spa'
					? /** @type {const} */ ('globe')
					: category.slug === 'beauty-clinics'
						? /** @type {const} */ ('building')
						: /** @type {const} */ ('sparkles')
		}))
	]);

	/**
	 * Where the customer is, once they have shared it. Held in memory only —
	 * never stored or sent anywhere but the search that measures distance.
	 * `accuracy` is the browser's own radius in metres (0 once the customer
	 * placed it by hand); `source` says which of the two it came from.
	 * @type {{ latitude: number, longitude: number, accuracy: number, source: 'device'|'map' } | null}
	 */
	let origin = $state(null);
	/**
	 * The point the searches measure from. Separate from `origin` so that a
	 * fix which only makes the accuracy circle tighter — same place, surer —
	 * redraws the circle without re-running every search.
	 * @type {{ latitude: number, longitude: number } | null}
	 */
	let searchAt = $state(null);
	let locating = $state(false);
	let locateMessage = $state(/** @type {string | null} */ (null));
	/** @type {AbortController | null} */
	let locateAbort = null;

	/** Past this, "near you" is a guess: say so, and invite a correction. */
	const ROUGH_FIX_M = 1000;
	/** The search's own precision need: salons within walking distance. */
	const GOOD_ENOUGH_M = 50;

	/**
	 * Takes a (better) fix from the device. The search re-runs only when the
	 * position really moves — by more than half the new accuracy, and at least
	 * 50 m — so a stream of near-identical fixes doesn't re-query each time.
	 * A position the customer placed by hand is never overridden.
	 * @param {import('$lib/map/geolocate.js').Fix} fix
	 */
	function takeFix(fix) {
		if (origin?.source === 'map') return;
		const next = /** @type {const} */ ({ ...fix, source: 'device' });
		if (!origin || metresBetween(origin, fix) > Math.max(GOOD_ENOUGH_M, fix.accuracy / 2)) {
			origin = next;
			moveSearch(fix);
		} else if (fix.accuracy < origin.accuracy) {
			// Same place, surer: update the circle without moving the search.
			origin = { ...origin, accuracy: fix.accuracy };
		}
	}

	/** The customer dragged the dot to where they really are. */
	/** @param {{ latitude: number, longitude: number }} position */
	function moveHere(position) {
		locateAbort?.abort();
		origin = { ...position, accuracy: 0, source: 'map' };
		moveSearch(position);
	}

	/**
	 * Moves the point searches measure from. A nearest-first list is a new list
	 * from a new point, so it starts again at its first page.
	 * @param {{ latitude: number, longitude: number }} position
	 */
	function moveSearch(position) {
		searchAt = { latitude: position.latitude, longitude: position.longitude };
		if (sortBy === 'nearest') offset = 0;
	}

	let originNote = $derived.by(() => {
		if (!origin) return null;
		if (origin.source === 'map') return t('Showing venues near the spot you placed on the map.');
		const within = describeAccuracy(origin.accuracy, t);
		return origin.accuracy > ROUGH_FIX_M
			? t(
					'Your device could only place you within about {within}, so "near you" may be off. Drag the blue dot on the map to where you are.',
					{ within }
				)
			: t('Showing venues near you — located to within about {within}.', { within });
	});

	/** How far "near you" reaches, in km. The API allows up to 100. */
	const NEAR_RADIUS_KM = 50;

	async function useMyLocation() {
		locating = true;
		locateMessage = null;
		locateAbort?.abort();
		const controller = new AbortController();
		locateAbort = controller;
		// A new request starts over, even from a position placed by hand.
		if (origin?.source === 'map') {
			origin = null;
			searchAt = null;
		}
		try {
			// The first answer a browser gives is often its fastest, not its best:
			// a Wi-Fi or IP guess that can be kilometres out. Show results from it
			// at once (`onfix`), then keep listening for a precise fix — the search
			// follows as it arrives, and stops early once it is good enough.
			const fix = await locate({
				onfix: takeFix,
				quickTimeoutMs: 10_000,
				refineMs: 10_000,
				preciseEnoughM: GOOD_ENOUGH_M,
				signal: controller.signal
			});
			takeFix(fix);
			return true;
		} catch (err) {
			const kind = err instanceof LocateError ? err.kind : 'unavailable';
			// Cancelled because the customer placed the dot themselves: that's
			// a result, not a failure.
			if (kind === 'cancelled') return origin !== null;
			locateMessage =
				kind === 'denied'
					? t(
							'Location is blocked for this site. Allow it from the address bar to see venues near you.'
						)
					: kind === 'insecure'
						? t('Your browser only shares location on secure (https) pages.')
						: t(
								'We couldn\'t find your location. Move the map to your area and press "Search this area" instead.'
							);
			return false;
		} finally {
			if (locateAbort === controller) {
				locating = false;
				locateAbort = null;
			}
		}
	}

	/** @param {string} value */
	async function changeSort(value) {
		if (value === 'nearest' && !origin && !(await useMyLocation())) {
			sortBy = 'recommended';
			return;
		}
		sortBy = value;
		offset = 0;
	}

	// Spotlight rows, shown above the results when nothing is being searched.
	let browsing = $derived(!term && !selectedCategory && !area && offset === 0);
	let topRated = $state(/** @type {import('$lib/api/discovery.js').ListingCard[]} */ ([]));
	let nearby = $state(/** @type {import('$lib/api/discovery.js').ListingCard[] | null} */ (null));

	$effect(() => {
		let cancelled = false;
		listCategories()
			.then((items) => {
				if (!cancelled) serviceCategories = items;
			})
			.catch((err) => {
				if (!cancelled) toastStore.fromError(err);
			});
		return () => {
			cancelled = true;
		};
	});

	$effect(() => {
		searchBusinesses({ sort: 'rating', limit: 8 })
			.then((page) => {
				// One card per salon, and only salons someone has actually rated.
				topRated = page.items
					.filter((item) => item.rating_count > 0)
					.filter(
						(item, index, all) =>
							all.findIndex((other) => other.business_id === item.business_id) === index
					)
					.slice(0, 4);
			})
			.catch(() => (topRated = []));
	});

	$effect(() => {
		if (!searchAt) return;
		const { latitude, longitude } = searchAt;
		nearby = null;
		searchBusinesses({ latitude, longitude, radiusKm: NEAR_RADIUS_KM, sort: 'distance', limit: 4 })
			.then((page) => (nearby = page.items))
			.catch(() => (nearby = []));
	});

	/** The page's sort names, as the API's `sort`. */
	const API_SORT = /** @type {Record<string, import('$lib/api/discovery.js').SearchSort>} */ ({
		recommended: 'default',
		rating: 'rating',
		nearest: 'distance',
		'price-low': 'price_asc',
		'price-high': 'price_desc'
	});

	/**
	 * One page of results. Every ordering — price included — is the server's,
	 * so page two continues page one instead of re-sorting twelve cards alone.
	 * @param {{ term: string, category: string, sort: string, bbox: string | null,
	 *   near: { latitude: number, longitude: number } | null, offset: number }} params
	 */
	async function search({ term, category, sort, bbox, near, offset }) {
		const ticket = ++searchTicket;
		loading = true;
		try {
			const page = await searchBusinesses({
				q: term || null,
				category: category || null,
				bbox,
				latitude: near?.latitude ?? null,
				longitude: near?.longitude ?? null,
				radiusKm: near ? NEAR_RADIUS_KM : null,
				sort: near ? 'distance' : sort === 'nearest' ? 'default' : (API_SORT[sort] ?? 'default'),
				// One extra row says whether a next page exists without counting them all.
				limit: limit + 1,
				offset
			});
			if (ticket !== searchTicket) return;
			const items = page.items || [];
			hasNextPage = items.length > limit;
			listings = items.slice(0, limit);
		} catch (err) {
			if (ticket === searchTicket) toastStore.fromError(err);
		} finally {
			if (ticket === searchTicket) loading = false;
		}
	}

	let pinsTicket = 0;

	/**
	 * @param {string | null} term
	 * @param {string | null} category
	 * @param {string | null} bbox
	 */
	async function loadPins(term, category, bbox) {
		// Answers can arrive out of order; only the newest request may land.
		const ticket = ++pinsTicket;
		pinsLoading = true;
		try {
			const collection = await mapBusinesses({ q: term, category, bbox });
			if (ticket !== pinsTicket) return;
			pins = collection.features.map((feature) => feature.properties);
			pinsTruncated = collection.truncated;
		} catch (err) {
			if (ticket !== pinsTicket) return;
			pins = [];
			pinsTruncated = false;
			toastStore.fromError(err);
		} finally {
			if (ticket === pinsTicket) pinsLoading = false;
		}
	}

	// Typing settles into `term` after a pause, and a new term starts at page one.
	$effect(() => {
		const next = q.trim();
		if (next === term) return;
		const timer = setTimeout(() => {
			term = next;
			offset = 0;
		}, 350);
		return () => clearTimeout(timer);
	});

	$effect(() => {
		search({
			term,
			category: selectedCategory,
			sort: sortBy,
			bbox: area,
			// Only a nearest-first list depends on where the customer is.
			near: sortBy === 'nearest' ? searchAt : null,
			offset
		});
	});

	// Pins have their own effect: they do not depend on the page or the sort, so
	// turning a page must not refetch them.
	$effect(() => {
		loadPins(term || null, selectedCategory || null, area);
	});

	/** @param {SubmitEvent} event */
	function handleSubmit(event) {
		event.preventDefault();
		term = q.trim();
		offset = 0;
		showResults();
	}

	function resetFilters() {
		q = '';
		term = '';
		selectedCategory = '';
		sortBy = 'recommended';
		area = null;
		offset = 0;
	}

	/** @param {number} next */
	function goToPage(next) {
		offset = Math.max(0, next);
		showResults();
	}

	/** @param {'list' | 'map'} next */
	async function showView(next) {
		view = next;
		if (next === 'list') return showResults();
		// The map is sized to fill the screen under the toolbar: scroll it there.
		await tick();
		mapBox?.scrollIntoView({ behavior: motion(), block: 'start' });
	}

	/** Brings the top of the results into view, unless it is already on screen. */
	function showResults() {
		if (!resultsTop || resultsTop.getBoundingClientRect().top >= 0) return;
		resultsTop.scrollIntoView({ behavior: motion(), block: 'start' });
	}

	/** @returns {ScrollBehavior} */
	function motion() {
		return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
	}

	const pagerButton =
		'inline-flex h-9 items-center gap-1.5 rounded-full px-4 text-sm font-medium text-fg-secondary focus-ring transition-colors duration-fast hover:bg-surface-muted hover:text-fg disabled:pointer-events-none disabled:opacity-40';

	let showingRange = $derived(
		offset > 0 || hasNextPage
			? t('Showing {from}–{to}', { from: offset + 1, to: offset + listings.length })
			: tp(listings.length, '{count} venue', '{count} venues')
	);

	/** @param {string | null} bbox */
	function searchArea(bbox) {
		area = bbox;
		offset = 0;
	}
</script>

<svelte:head>
	<title>{t('Discover salons, spas & clinics')} — NOVA</title>
	<meta
		name="description"
		content={t(
			'Search salons, spas, massage centres, hammams and beauty clinics in Riyadh, Jeddah, and Al Khobar, and book directly with live availability.'
		)}
	/>
</svelte:head>

<!-- Search header -->
<section class="relative isolate overflow-hidden">
	<GradientBlob variant="hero" />
	<!-- A hairline that fades out at both ends, in place of a hard border. -->
	<div
		class="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-line-strong to-transparent"
		aria-hidden="true"
	></div>

	<Container size="lg" class="relative z-10 pt-12 pb-10 sm:pt-20 sm:pb-14">
		<div class="mx-auto max-w-3xl text-center">
			<p
				class="inline-flex items-center gap-2 rounded-full border border-line bg-surface/70 px-3.5 py-1.5 text-xs font-medium text-fg-secondary shadow-card backdrop-blur"
			>
				<span class="relative flex size-2">
					<span
						class="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-60 motion-reduce:hidden"
					></span>
					<span class="relative inline-flex size-2 rounded-full bg-emerald-500"></span>
				</span>
				{t('Live availability in Riyadh, Jeddah & Khobar')}
			</p>
			<h1 class="mt-6 text-display-xl font-semibold tracking-tight text-balance text-fg">
				{t('Find your next treatment')}
			</h1>
			<div
				class="mx-auto mt-5 h-1 w-16 rounded-full"
				style="background-image: var(--gradient-ink)"
				aria-hidden="true"
			></div>
			<p class="mx-auto mt-5 max-w-xl text-body-lg text-pretty text-fg-muted">
				{t('Book a real, held slot in seconds — confirmed instantly on WhatsApp.')}
			</p>
		</div>

		<form
			onsubmit={handleSubmit}
			role="search"
			class="mx-auto mt-9 flex max-w-3xl flex-col gap-2 rounded-panel border border-line bg-surface/90 p-2 shadow-overlay ring-1 ring-white/40 backdrop-blur-xl transition-shadow duration-base focus-within:border-line-strong sm:flex-row sm:items-center dark:ring-white/5"
		>
			<div class="relative flex-1">
				<Icon
					name="search"
					class="pointer-events-none absolute start-4 top-1/2 size-5 -translate-y-1/2 text-fg-subtle"
				/>
				<input
					type="search"
					aria-label={t('Search venues or services')}
					placeholder={t('Venue or treatment — e.g. Thai massage, HydraFacial, balayage')}
					bind:value={q}
					class="h-12 w-full rounded-card border-0 bg-transparent ps-12 pe-3 text-[15px] text-fg placeholder:text-fg-subtle focus:ring-0 focus:outline-none"
				/>
			</div>
			<div class="hidden h-8 w-px bg-line sm:block"></div>
			<!-- Where to search comes from the device (or the map), never from a list of cities. -->
			<Button
				type="button"
				variant="ghost"
				size="lg"
				class="sm:w-52"
				loading={locating}
				onclick={async () => {
					if (origin) await useMyLocation();
					await changeSort('nearest');
				}}
				aria-pressed={sortBy === 'nearest'}
			>
				{#if !locating}<Icon name="map-pin" class="size-4" />{/if}
				{locating
					? t('Finding your location…')
					: origin
						? t('Update my location')
						: t('Use my location')}
			</Button>
			<Button type="submit" size="lg" class="sm:px-8">{t('Search')}</Button>
		</form>
		{#if locateMessage || originNote}
			<div
				class="mx-auto mt-3 flex max-w-xl flex-wrap items-center justify-center gap-x-3 gap-y-1 text-center"
			>
				<p
					class={[
						'text-xs',
						origin && origin.source === 'device' && origin.accuracy > ROUGH_FIX_M
							? 'text-amber-700 dark:text-amber-400'
							: 'text-fg-muted'
					]}
					role="status"
				>
					{locateMessage ?? originNote}
				</p>
				{#if origin && origin.source === 'device' && origin.accuracy > ROUGH_FIX_M && view === 'list'}
					<button
						type="button"
						class="rounded-sm text-xs font-semibold text-accent underline-offset-4 focus-ring hover:underline"
						onclick={() => showView('map')}
					>
						{t('Correct it on the map')}
					</button>
				{/if}
			</div>
		{/if}

		<ul
			class="mx-auto mt-6 flex max-w-3xl flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-fg-muted"
		>
			<li class="inline-flex items-center gap-1.5">
				<Icon name="zap" class="size-3.5 text-accent" />{t('Instant confirmation')}
			</li>
			<li class="inline-flex items-center gap-1.5">
				<Icon name="clock" class="size-3.5 text-accent" />{t('Real, held time slots')}
			</li>
			<li class="inline-flex items-center gap-1.5">
				<Icon name="shield-check" class="size-3.5 text-accent" />{t(
					'Pay securely with Mada or Apple Pay'
				)}
			</li>
		</ul>

		<!-- One scrolling row on a phone, centred and wrapped from `sm` up. -->
		<div
			class="-mx-4 mt-8 flex [scrollbar-width:none] gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:justify-center sm:overflow-visible sm:px-0"
			role="group"
			aria-label={t('Category')}
		>
			{#each categories as cat (cat.id)}
				<button
					type="button"
					aria-pressed={selectedCategory === cat.id}
					onclick={() => {
						selectedCategory = cat.id;
						area = null;
						offset = 0;
					}}
					class={[
						'inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-4 text-xs font-medium focus-ring transition-[background-color,border-color,color,box-shadow] duration-fast',
						selectedCategory === cat.id
							? 'border-transparent bg-fg text-canvas shadow-raised'
							: 'border-line bg-surface/80 text-fg-secondary backdrop-blur hover:border-line-strong hover:text-fg'
					]}
				>
					<Icon name={cat.icon} class="size-3.5" />
					{t(cat.name)}
				</button>
			{/each}
		</div>
	</Container>
</section>

{#snippet cover(
	/** @type {import('$lib/api/discovery.js').ListingCard} */ listing,
	/** @type {string} */ shape
)}
	{#if listing.cover_url && !brokenCovers.has(listing.cover_url)}
		<img
			src={apiAssetUrl(listing.cover_url)}
			alt=""
			loading="lazy"
			onerror={() => listing.cover_url && brokenCovers.add(listing.cover_url)}
			class={`w-full object-cover ${shape}`}
		/>
	{:else}
		<!-- No photo (or one that would not load): the name's initial on the brand
		     gradient, so every card keeps one shape. -->
		<div
			class={`flex w-full items-center justify-center text-4xl font-semibold text-white/90 ${shape}`}
			style="background-image: var(--gradient-hero)"
			aria-hidden="true"
		>
			{pickBilingual(listing, 'name').trim().charAt(0).toUpperCase()}
		</div>
	{/if}
{/snippet}

{#snippet spotlightCard(/** @type {import('$lib/api/discovery.js').ListingCard} */ listing)}
	<a
		href={resolve('/discover/[slug]', { slug: listing.slug })}
		class="group flex h-full flex-col overflow-hidden rounded-card border border-line bg-surface shadow-card focus-ring transition-[border-color,box-shadow,transform] duration-base ease-out-premium hover:-translate-y-0.5 hover:border-line-strong hover:shadow-raised"
	>
		<div class="overflow-hidden">
			{@render cover(
				listing,
				'aspect-[16/10] transition-transform duration-slow ease-out-premium group-hover:scale-[1.04]'
			)}
		</div>
		<div class="flex flex-1 flex-col p-4">
			<p class="truncate font-semibold text-fg group-hover:text-accent">
				{pickBilingual(listing, 'name')}
			</p>
			<p class="mt-0.5 flex items-center gap-1 truncate text-xs text-fg-muted">
				<Icon name="map-pin" class="size-3" />
				{pickBilingual(listing, 'location_name') || listing.city}
				{#if listing.distance_km != null}
					<span aria-hidden="true">·</span>
					<span class="shrink-0 font-medium text-fg-secondary"
						>{t('{n} km', { n: listing.distance_km })}</span
					>
				{/if}
			</p>
			<div class="mt-auto flex items-center justify-between gap-2 pt-4">
				<RatingStars
					average={listing.rating_average}
					count={listing.rating_count}
					size="sm"
					compact
				/>
				<span class="text-xs text-fg-muted">
					{t('from')}
					<span class="font-semibold text-fg tabular-nums">
						{formatMoney(listing.starting_price, listing.currency ?? 'SAR')}
					</span>
				</span>
			</div>
		</div>
	</a>
{/snippet}

{#snippet sectionHeading(
	/** @type {string} */ id,
	/** @type {'map-pin' | 'star'} */ icon,
	/** @type {string} */ title,
	/** @type {(() => void) | null} */ onall
)}
	<div class="mb-4 flex items-center justify-between gap-3">
		<h2 {id} class="flex items-center gap-2.5 text-base font-semibold tracking-tight text-fg">
			<span class="flex size-7 items-center justify-center rounded-full bg-accent-soft text-accent">
				<Icon name={icon} class="size-3.5" />
			</span>
			{title}
		</h2>
		{#if onall}
			<Button size="sm" variant="ghost" onclick={onall}>
				{t('See all')}
				<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
			</Button>
		{/if}
	</div>
{/snippet}

<Container size="lg" class="py-10 sm:py-14">
	{#if browsing}
		<div class="mb-14 grid gap-10 lg:grid-cols-2">
			<section aria-labelledby="near-heading">
				{@render sectionHeading(
					'near-heading',
					'map-pin',
					t('Near you'),
					origin ? () => changeSort('nearest') : null
				)}
				{#if !origin}
					<div
						class="relative isolate flex flex-col items-start gap-4 overflow-hidden rounded-card border border-line bg-surface p-5 shadow-card sm:flex-row sm:items-center"
					>
						<GradientBlob variant="corner" class="opacity-60" />
						<span
							class="flex size-11 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent ring-4 ring-accent-soft/40"
						>
							<Icon name="map-pin" class="size-5" />
						</span>
						<p class="flex-1 text-sm text-fg-muted">
							{t(
								"Share your location to see the closest spas, salons and clinics. It's only used for this search."
							)}
						</p>
						<Button size="sm" loading={locating} onclick={useMyLocation}
							>{t('Use my location')}</Button
						>
					</div>
				{:else if nearby === null}
					<div class="grid grid-cols-2 gap-3">
						{#each [0, 1, 2, 3] as n (n)}<Skeleton class="h-28 rounded-card" />{/each}
					</div>
				{:else if nearby.length === 0}
					<p class="rounded-card border border-line bg-surface p-5 text-sm text-fg-muted">
						{t('No venues within {km} km of you yet.', { km: NEAR_RADIUS_KM })}
					</p>
				{:else}
					<div class="grid grid-cols-2 gap-3">
						{#each nearby as listing (listing.location_id)}
							{@render spotlightCard(listing)}
						{/each}
					</div>
				{/if}
			</section>

			<section aria-labelledby="top-heading">
				{@render sectionHeading(
					'top-heading',
					'star',
					t('Top rated'),
					topRated.length > 0 ? () => changeSort('rating') : null
				)}
				{#if topRated.length === 0}
					<p class="rounded-card border border-line bg-surface p-5 text-sm text-fg-muted">
						{t('Ratings appear here once customers rate their visits.')}
					</p>
				{:else}
					<div class="grid grid-cols-2 gap-3">
						{#each topRated as listing (listing.location_id)}
							{@render spotlightCard(listing)}
						{/each}
					</div>
				{/if}
			</section>
		</div>
	{/if}

	<section aria-labelledby="results-heading">
		<div bind:this={resultsTop} class="scroll-mt-24 sm:scroll-mt-28">
			<p class="text-xs font-semibold tracking-[0.14em] text-accent uppercase">
				{t('Book a treatment')}
			</p>
			<h2 id="results-heading" class="mt-1.5 text-display-md font-semibold tracking-tight text-fg">
				{browsing ? t('All venues') : t('Results')}
			</h2>
		</div>

		<!-- The toolbar follows the page down, just under the site header. -->
		<div
			class="sticky top-20 z-30 -mx-2 mt-5 mb-6 flex flex-wrap items-center justify-between gap-3 rounded-panel border border-line bg-surface/85 px-3 py-2 shadow-card backdrop-blur-xl sm:top-22 sm:mx-0"
		>
			<div class="flex min-w-0 items-center gap-2 ps-1">
				<p class="text-sm font-medium text-fg-secondary tabular-nums" aria-live="polite">
					{loading && listings.length === 0 ? t('Searching…') : showingRange}
				</p>
				{#if term || selectedCategory || area}
					<Button size="sm" variant="ghost" onclick={resetFilters}>
						<Icon name="x" class="size-3.5" />
						{t('Clear filters')}
					</Button>
				{/if}
			</div>

			<div class="flex items-center gap-2">
				<label for="sort-select" class="sr-only">{t('Sort by')}</label>
				<select
					id="sort-select"
					value={sortBy}
					onchange={(event) => changeSort(event.currentTarget.value)}
					class={`${fieldBase} ${fieldBorder(false)} h-9 w-auto pe-9 text-[13px]`}
				>
					<option value="recommended">{t('Recommended')}</option>
					<option value="rating">{t('Top rated')}</option>
					<option value="nearest">{t('Nearest to me')}</option>
					<option value="price-low">{t('Price: low to high')}</option>
					<option value="price-high">{t('Price: high to low')}</option>
				</select>
				<div
					class="inline-flex rounded-full bg-surface-muted p-1"
					role="group"
					aria-label={t('Show results as')}
				>
					{#each views as mode (mode.id)}
						<button
							type="button"
							onclick={() => showView(mode.id)}
							aria-pressed={view === mode.id}
							class={[
								'inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-xs font-medium focus-ring transition-[background-color,color,box-shadow] duration-fast',
								view === mode.id
									? 'bg-surface text-fg shadow-card ring-1 ring-line'
									: 'text-fg-muted hover:text-fg'
							]}
						>
							<Icon name={mode.icon} class="size-3.5" />
							{t(mode.label)}
						</button>
					{/each}
				</div>
			</div>
		</div>

		<div class={[view === 'map' && 'hidden']}>
			{#if loading && listings.length === 0}
				<div class="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
					{#each [0, 1, 2] as n (n)}
						<div class="overflow-hidden rounded-panel border border-line bg-surface shadow-card">
							<Skeleton class="aspect-[4/3] w-full rounded-none" />
							<div class="space-y-3 p-5">
								<Skeleton class="h-5 w-2/3" />
								<Skeleton class="h-3 w-1/3" />
								<Skeleton class="mt-6 h-9 w-full rounded-control" />
							</div>
						</div>
					{/each}
				</div>
			{:else if listings.length === 0}
				{#if offset > 0}
					<EmptyState
						title={t('No more venues')}
						description={t('This page is past the end of the results.')}
					>
						{#snippet icon()}<Icon name="search" class="size-6" />{/snippet}
						{#snippet action()}
							<Button variant="outline" onclick={() => goToPage(0)}
								>{t('Back to the first page')}</Button
							>
						{/snippet}
					</EmptyState>
				{:else}
					<EmptyState
						title={t('No venues match')}
						description={t('Try a different search term or category, or move the map.')}
					>
						{#snippet icon()}<Icon name="search" class="size-6" />{/snippet}
						{#snippet action()}
							<Button variant="outline" onclick={resetFilters}>{t('Reset filters')}</Button>
						{/snippet}
					</EmptyState>
				{/if}
			{:else}
				<!-- The page being replaced stays on screen, dimmed, until the next one
				     arrives: no jump to skeletons and back on every page turn. -->
				<div
					class={[
						'grid grid-cols-1 gap-6 transition-opacity duration-base sm:grid-cols-2 lg:grid-cols-3',
						loading && 'pointer-events-none opacity-50'
					]}
					aria-busy={loading}
				>
					{#each listings as listing (listing.business_id + listing.location_id)}
						<article
							class="group relative flex flex-col overflow-hidden rounded-panel border border-line bg-surface shadow-card transition-[border-color,box-shadow,transform] duration-base ease-out-premium hover:-translate-y-1 hover:border-line-strong hover:shadow-raised"
						>
							<div class="relative overflow-hidden">
								{@render cover(
									listing,
									'aspect-[4/3] transition-transform duration-slow ease-out-premium group-hover:scale-[1.04]'
								)}
								<div
									class="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/45 via-black/0 to-black/10"
									aria-hidden="true"
								></div>
								<span
									class="absolute start-3 top-3 inline-flex items-center gap-1 rounded-full bg-surface/90 px-2.5 py-1 text-[11px] font-semibold text-fg shadow-card backdrop-blur"
								>
									<Icon name="map-pin" class="size-3 text-accent" />
									{listing.city ? t(listing.city) : t('KSA')}
								</span>
								{#if listing.distance_km != null}
									<span
										class="absolute end-3 top-3 rounded-full bg-black/55 px-2.5 py-1 text-[11px] font-semibold text-white tabular-nums backdrop-blur"
									>
										{t('{n} km', { n: listing.distance_km })}
									</span>
								{/if}
								{#if listing.starting_price != null}
									<p
										class="absolute start-4 bottom-3 text-xs font-medium text-white/90 drop-shadow"
									>
										{t('From')}
										<span class="text-base font-semibold text-white tabular-nums">
											{formatMoney(listing.starting_price, listing.currency ?? 'SAR')}
										</span>
									</p>
								{/if}
							</div>

							<div class="flex flex-1 flex-col p-5">
								<h3
									class="text-[17px] leading-snug font-semibold tracking-tight text-fg transition-colors group-hover:text-accent"
								>
									{pickBilingual(listing, 'name')}
								</h3>
								{#if i18n.locale === 'en' && listing.name_ar}
									<p class="mt-0.5 w-fit text-xs text-fg-muted" dir="rtl" lang="ar">
										{listing.name_ar}
									</p>
								{:else if i18n.locale === 'ar' && listing.name_en}
									<p class="mt-0.5 w-fit text-xs text-fg-muted" dir="ltr" lang="en">
										{listing.name_en}
									</p>
								{/if}

								<div
									class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-fg-muted"
								>
									<RatingStars
										average={listing.rating_average}
										count={listing.rating_count}
										size="sm"
										compact
									/>
									<span class="inline-flex min-w-0 items-center gap-1">
										<Icon name="building" class="size-3.5" />
										<span class="truncate"
											>{pickBilingual(listing, 'location_name') || listing.city}</span
										>
									</span>
								</div>

								{#if pickBilingual(listing, 'description')}
									<p class="mt-3 line-clamp-2 text-sm text-fg-muted">
										{pickBilingual(listing, 'description')}
									</p>
								{/if}

								<div class="mt-auto grid grid-cols-2 gap-2 pt-5">
									<Button
										size="sm"
										variant="outline"
										fullWidth
										onclick={() => (quickViewSalon = listing)}
									>
										{t('Quick View')}
									</Button>
									<Button
										href={resolve('/discover/[slug]', { slug: listing.slug })}
										size="sm"
										fullWidth
									>
										{t('Book Now')}
									</Button>
								</div>
							</div>
						</article>
					{/each}
				</div>

				{#if offset > 0 || hasNextPage}
					<nav class="mt-12 flex flex-col items-center gap-3" aria-label={t('Pagination')}>
						<div
							class="inline-flex items-center gap-1 rounded-full border border-line bg-surface p-1 shadow-card"
						>
							<button
								type="button"
								class={pagerButton}
								disabled={offset === 0 || loading}
								onclick={() => goToPage(offset - limit)}
							>
								<Icon name="chevron-left" class="size-4 rtl:rotate-180" />
								{t('Previous')}
							</button>
							<span
								class="flex h-9 min-w-9 items-center justify-center rounded-full bg-fg px-3 text-sm font-semibold text-canvas tabular-nums"
								aria-current="page"
							>
								{t('Page {page}', { page: Math.floor(offset / limit) + 1 })}
							</span>
							<button
								type="button"
								class={pagerButton}
								disabled={!hasNextPage || loading}
								onclick={() => goToPage(offset + limit)}
							>
								{t('Next')}
								<Icon name="chevron-right" class="size-4 rtl:rotate-180" />
							</button>
						</div>
						<p class="text-xs text-fg-muted tabular-nums">{showingRange}</p>
					</nav>
				{/if}
			{/if}
		</div>

		<div bind:this={mapBox} class={['scroll-mt-40 sm:scroll-mt-44', view === 'list' && 'hidden']}>
			<ListingsMap
				listings={pins}
				fit={area === null}
				loading={pinsLoading}
				truncated={pinsTruncated}
				areaActive={area !== null}
				onselect={(listing) => (quickViewSalon = listing)}
				onsearcharea={searchArea}
				onclear={() => searchArea(null)}
				here={origin}
				onmovehere={moveHere}
				class="h-[calc(100dvh-11rem)] min-h-[26rem] shadow-raised sm:h-[calc(100dvh-12rem)]"
			/>
		</div>
	</section>
</Container>

<Modal
	open={quickViewSalon !== null}
	title={quickViewSalon ? pickBilingual(quickViewSalon, 'name') : ''}
	description={quickViewSalon
		? i18n.locale === 'ar'
			? quickViewSalon.name_en
			: quickViewSalon.name_ar
		: null}
	onclose={() => (quickViewSalon = null)}
>
	{#if quickViewSalon}
		{#if quickViewSalon.cover_url}
			<img
				src={apiAssetUrl(quickViewSalon.cover_url)}
				alt=""
				class="mb-4 aspect-[16/9] w-full rounded-card object-cover"
			/>
		{/if}
		<div class="mb-4">
			<RatingStars average={quickViewSalon.rating_average} count={quickViewSalon.rating_count} />
		</div>
		{#if pickBilingual(quickViewSalon, 'description')}
			<p class="text-sm text-fg-secondary">{pickBilingual(quickViewSalon, 'description')}</p>
		{/if}
		<dl class="mt-5 divide-y divide-line-subtle rounded-card border border-line text-sm">
			<div class="flex items-center gap-3 px-4 py-3">
				<Icon name="map-pin" class="size-4 text-accent" />
				<dt class="sr-only">{t('Location')}</dt>
				<dd class="text-fg-secondary">
					{[
						pickBilingual(quickViewSalon, 'location_name'),
						quickViewSalon.city && t(quickViewSalon.city)
					]
						.filter(Boolean)
						.join(t(', '))}
				</dd>
			</div>
			<div class="flex items-center gap-3 px-4 py-3">
				<Icon name="credit-card" class="size-4 text-accent" />
				<dt class="sr-only">{t('Payment')}</dt>
				<dd class="text-fg-secondary">{t('Mada, Apple Pay, Visa & Mastercard')}</dd>
			</div>
			<div class="flex items-center gap-3 px-4 py-3">
				<Icon name="sparkles" class="size-4 text-accent" />
				<dt class="sr-only">{t('Price')}</dt>
				<dd class="text-fg-secondary">
					{t('Treatments from')}
					<span class="font-semibold text-fg tabular-nums">
						{formatMoney(quickViewSalon.starting_price, quickViewSalon.currency ?? 'SAR')}
					</span>
				</dd>
			</div>
		</dl>
	{/if}
	{#snippet footer()}
		<Button variant="ghost" onclick={() => (quickViewSalon = null)}>{t('Close')}</Button>
		{#if quickViewSalon}
			<Button href={resolve('/discover/[slug]', { slug: quickViewSalon.slug })}>
				{t('View Full Menu')}
			</Button>
		{/if}
	{/snippet}
</Modal>

<AssistantLauncher
	marketplace
	title={t('NOVA assistant')}
	subtitle={t('Find a spa, salon or clinic and book it')}
	intro={t(
		'Tell me what you need, where and when. I search every business on NOVA, find a free time, and book it once you say yes.'
	)}
	starters={[
		t('Find me a spa in Riyadh this weekend'),
		t('I need a massage tomorrow afternoon'),
		t('Which clinics do laser hair removal near Jeddah?')
	]}
/>
