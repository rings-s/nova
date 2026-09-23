<script>
	import { mapBusinesses, searchBusinesses } from '$lib/api/discovery.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { pickBilingual } from '$lib/utils/bilingual.js';
	import { formatMoney } from '$lib/utils/money.js';
	import { resolve } from '$app/paths';
	import Container from '$lib/components/marketing/Container.svelte';
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';
	import ListingsMap from '$lib/components/map/ListingsMap.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import { fieldBase, fieldBorder } from '$lib/components/ui/styles.js';
	import RatingStars from '$lib/components/review/RatingStars.svelte';
	import { apiAssetUrl } from '$lib/api/client.js';
	import { locate, LocateError } from '$lib/map/geolocate.js';

	let q = $state('');
	let selectedCity = $state('');
	let selectedCategory = $state('');
	let sortBy = $state('recommended');
	let offset = $state(0);
	const limit = 12;

	let loading = $state(true);
	let listings = $state(/** @type {any[]} */ ([]));

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
	// Below `lg` the list and the map take turns on the screen; from `lg` up they
	// sit side by side and this is ignored.
	/** @type {('list' | 'map')[]} */
	const views = ['list', 'map'];
	let view = $state(views[0]);

	// Quick View Modal
	let quickViewSalon = $state(/** @type {any | null} */ (null));

	const cities = [
		{ id: '', name: 'All Cities' },
		{ id: 'Riyadh', name: 'Riyadh (الرياض)' },
		{ id: 'Jeddah', name: 'Jeddah (جدة)' },
		{ id: 'Al Khobar', name: 'Al Khobar (الخبر)' }
	];

	/** @type {{ id: string, name: string, icon: import('$lib/components/ui/Icon.svelte').IconName }[]} */
	const categories = [
		{ id: '', name: 'All Services', icon: 'sparkles' },
		{ id: 'Hair', name: 'Hair & Styling', icon: 'zap' },
		{ id: 'Skincare', name: 'Skincare & Facials', icon: 'sparkles' },
		{ id: 'Spa', name: 'Hammam & Spa', icon: 'globe' },
		{ id: 'Nail', name: 'Nails & Brows', icon: 'check' },
		{ id: 'Massage', name: 'Massage & Recovery', icon: 'users' }
	];

	/**
	 * Where the customer is, once they have shared it. Held in memory only —
	 * never stored or sent anywhere but the search that measures distance.
	 * @type {{ latitude: number, longitude: number } | null}
	 */
	let origin = $state(null);
	let locating = $state(false);
	let locateMessage = $state(/** @type {string | null} */ (null));

	/** How far "near you" reaches, in km. The API allows up to 100. */
	const NEAR_RADIUS_KM = 50;

	async function useMyLocation() {
		locating = true;
		locateMessage = null;
		try {
			// A rough, quick fix is plenty to rank salons by distance: skip the
			// refinement step the branch-pin picker needs.
			const fix = await locate({ onfix: () => {}, quickTimeoutMs: 10_000, refineMs: 0 });
			origin = { latitude: fix.latitude, longitude: fix.longitude };
			return true;
		} catch (err) {
			const kind = err instanceof LocateError ? err.kind : 'unavailable';
			locateMessage =
				kind === 'denied'
					? 'Location is blocked for this site. Allow it from the address bar to see salons near you.'
					: kind === 'insecure'
						? 'Your browser only shares location on secure (https) pages.'
						: "We couldn't find your location. Pick a city instead.";
			return false;
		} finally {
			locating = false;
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
	let browsing = $derived(!q && !selectedCity && !selectedCategory && !area && offset === 0);
	let topRated = $state(/** @type {import('$lib/api/discovery.js').ListingCard[]} */ ([]));
	let nearby = $state(/** @type {import('$lib/api/discovery.js').ListingCard[] | null} */ (null));

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
		if (!origin) return;
		const { latitude, longitude } = origin;
		nearby = null;
		searchBusinesses({ latitude, longitude, radiusKm: NEAR_RADIUS_KM, sort: 'distance', limit: 4 })
			.then((page) => (nearby = page.items))
			.catch(() => (nearby = []));
	});

	async function search() {
		loading = true;
		try {
			const combinedQ = [q, selectedCategory].filter(Boolean).join(' ');
			const near = sortBy === 'nearest' ? origin : null;
			const page = await searchBusinesses({
				q: combinedQ || null,
				city: selectedCity || null,
				bbox: area,
				latitude: near?.latitude ?? null,
				longitude: near?.longitude ?? null,
				radiusKm: near ? NEAR_RADIUS_KM : null,
				sort: near ? 'distance' : sortBy === 'rating' ? 'rating' : 'default',
				limit,
				offset
			});
			let items = page.items || [];

			if (sortBy === 'price-low') {
				items = [...items].sort(
					(a, b) => parseFloat(a.starting_price || '0') - parseFloat(b.starting_price || '0')
				);
			} else if (sortBy === 'price-high') {
				items = [...items].sort(
					(a, b) => parseFloat(b.starting_price || '0') - parseFloat(a.starting_price || '0')
				);
			}
			listings = items;
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			loading = false;
		}
	}

	let pinsTicket = 0;

	/**
	 * @param {string | null} term
	 * @param {string | null} city
	 * @param {string | null} bbox
	 */
	async function loadPins(term, city, bbox) {
		// Answers can arrive out of order; only the newest request may land.
		const ticket = ++pinsTicket;
		pinsLoading = true;
		try {
			const collection = await mapBusinesses({ q: term, city, bbox });
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

	$effect(() => {
		offset;
		selectedCity;
		selectedCategory;
		sortBy;
		area;
		origin;
		search();
	});

	// Pins have their own effect: they do not depend on the page or the sort, so
	// turning a page must not refetch them. Debounced, because the search box
	// re-runs the search on every keystroke and the discovery routes share one
	// 60-requests-a-minute allowance per address.
	$effect(() => {
		const term = [q, selectedCategory].filter(Boolean).join(' ') || null;
		const city = selectedCity || null;
		const bbox = area;
		const timer = setTimeout(() => loadPins(term, city, bbox), 300);
		return () => clearTimeout(timer);
	});

	/** @param {SubmitEvent} event */
	function handleSubmit(event) {
		event.preventDefault();
		offset = 0;
		search();
	}

	function resetFilters() {
		q = '';
		selectedCity = '';
		selectedCategory = '';
		sortBy = 'recommended';
		area = null;
		offset = 0;
		search();
	}

	/** @param {string | null} bbox */
	function searchArea(bbox) {
		area = bbox;
		offset = 0;
	}
</script>

<svelte:head>
	<title>Discover salons &amp; spas — NOVA</title>
	<meta
		name="description"
		content="Search beauty salons, spas, and hammams in Riyadh, Jeddah, and Al Khobar, and book directly with live availability."
	/>
</svelte:head>

<!-- Search header -->
<section class="relative overflow-hidden border-b border-line bg-surface">
	<GradientBlob variant="hero" />

	<Container size="lg" class="relative z-10 py-12 sm:py-16">
		<div class="mx-auto max-w-3xl text-center">
			<p
				class="inline-flex items-center gap-2 rounded-full border border-line bg-surface/80 px-3 py-1 text-xs font-medium text-fg-secondary backdrop-blur"
			>
				<span class="size-1.5 animate-pulse rounded-full bg-emerald-500"></span>
				Live availability in Riyadh, Jeddah &amp; Khobar
			</p>
			<h1 class="mt-5 text-display-xl font-semibold tracking-tight text-fg">
				Find your next salon or spa
			</h1>
			<p class="mt-3 text-body-lg text-fg-muted">
				Book a real, held slot in seconds — confirmed instantly on WhatsApp.
			</p>
		</div>

		<form
			onsubmit={handleSubmit}
			role="search"
			class="mx-auto mt-8 flex max-w-3xl flex-col gap-2 rounded-panel border border-line bg-surface p-2 shadow-raised sm:flex-row sm:items-center"
		>
			<div class="relative flex-1">
				<Icon
					name="search"
					class="pointer-events-none absolute start-3.5 top-1/2 size-5 -translate-y-1/2 text-fg-subtle"
				/>
				<input
					type="text"
					aria-label="Search salons or services"
					placeholder="Salon or service — e.g. HydraFacial, balayage"
					bind:value={q}
					class="h-12 w-full rounded-card border-0 bg-transparent ps-11 pe-3 text-[15px] text-fg placeholder:text-fg-subtle focus:ring-0 focus:outline-none"
				/>
			</div>
			<div class="hidden h-7 w-px bg-line sm:block"></div>
			<div class="relative sm:w-48">
				<Icon
					name="map-pin"
					class="pointer-events-none absolute start-3 top-1/2 z-10 size-4 -translate-y-1/2 text-fg-subtle"
				/>
				<select
					aria-label="City"
					bind:value={selectedCity}
					onchange={() => (area = null)}
					class="h-12 w-full rounded-card border-0 bg-transparent ps-9 text-sm text-fg-secondary focus:ring-0 focus:outline-none"
				>
					{#each cities as c (c.id)}
						<option value={c.id}>{c.name}</option>
					{/each}
				</select>
			</div>
			<Button type="submit" size="lg" class="sm:px-7">Search</Button>
		</form>
		<div class="mt-4 flex justify-center">
			<Button
				variant="ghost"
				size="sm"
				loading={locating}
				onclick={() => changeSort('nearest')}
				aria-pressed={sortBy === 'nearest'}
			>
				{#if !locating}<Icon name="map-pin" class="size-4" />{/if}
				{origin ? 'Showing salons near you' : 'Use my location'}
			</Button>
		</div>
		{#if locateMessage}
			<p class="mx-auto mt-2 max-w-md text-center text-xs text-fg-muted" role="status">
				{locateMessage}
			</p>
		{/if}

		<div
			class="mt-6 flex flex-wrap items-center justify-center gap-2"
			role="group"
			aria-label="Category"
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
						'inline-flex h-8 items-center gap-1.5 rounded-full border px-3.5 text-xs font-medium focus-ring transition-colors duration-fast',
						selectedCategory === cat.id
							? 'border-transparent bg-slate-900 text-white dark:bg-white dark:text-slate-900'
							: 'border-line bg-surface text-fg-secondary hover:border-line-strong hover:text-fg'
					].join(' ')}
				>
					<Icon name={cat.icon} class="size-3.5" />
					{cat.name}
				</button>
			{/each}
		</div>
	</Container>
</section>

{#snippet cover(
	/** @type {import('$lib/api/discovery.js').ListingCard} */ listing,
	/** @type {string} */ shape
)}
	{#if listing.cover_url}
		<img
			src={apiAssetUrl(listing.cover_url)}
			alt=""
			loading="lazy"
			class={`w-full object-cover ${shape}`}
		/>
	{:else}
		<!-- No photo yet: the name's initial on the brand gradient, so every card keeps one shape. -->
		<div
			class={`flex w-full items-center justify-center text-3xl font-semibold text-white/90 ${shape}`}
			style="background-image: var(--gradient-hero)"
			aria-hidden="true"
		>
			{pickBilingual(listing, 'name', 'en').trim().charAt(0).toUpperCase()}
		</div>
	{/if}
{/snippet}

{#snippet spotlightCard(/** @type {import('$lib/api/discovery.js').ListingCard} */ listing)}
	<a
		href={resolve('/discover/[slug]', { slug: listing.slug })}
		class="group flex h-full flex-col overflow-hidden rounded-card border border-line bg-surface shadow-card focus-ring transition-[border-color,box-shadow,transform] duration-base ease-out-premium hover:-translate-y-0.5 hover:border-line-strong hover:shadow-raised"
	>
		{@render cover(listing, 'aspect-[16/10]')}
		<div class="flex flex-1 flex-col p-4">
			<p class="truncate font-semibold text-fg group-hover:text-accent">
				{pickBilingual(listing, 'name', 'en')}
			</p>
			<p class="mt-0.5 flex items-center gap-1 truncate text-xs text-fg-muted">
				<Icon name="map-pin" class="size-3" />
				{listing.location_name_en || listing.city}
				{#if listing.distance_km != null}
					<span aria-hidden="true">·</span>
					<span class="shrink-0 font-medium text-fg-secondary">{listing.distance_km} km</span>
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
					from
					<span class="font-semibold text-fg tabular-nums">
						{formatMoney(listing.starting_price, listing.currency ?? 'SAR', 'en')}
					</span>
				</span>
			</div>
		</div>
	</a>
{/snippet}

<Container size="lg" class="py-8 sm:py-12">
	{#if browsing}
		<div class="mb-12 grid gap-10 lg:grid-cols-2">
			<section aria-labelledby="near-heading">
				<div class="mb-4 flex items-center justify-between gap-3">
					<h2
						id="near-heading"
						class="flex items-center gap-2 text-base font-semibold tracking-tight text-fg"
					>
						<Icon name="map-pin" class="size-4 text-accent" />
						Near you
					</h2>
					{#if origin}
						<Button size="sm" variant="ghost" onclick={() => changeSort('nearest')}>
							See all
							<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
						</Button>
					{/if}
				</div>
				{#if !origin}
					<div
						class="flex flex-col items-start gap-4 rounded-card border border-dashed border-line-strong bg-surface-sunken/60 p-5 sm:flex-row sm:items-center"
					>
						<span
							class="flex size-10 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent"
						>
							<Icon name="map-pin" class="size-5" />
						</span>
						<p class="flex-1 text-sm text-fg-muted">
							Share your location to see the closest salons and spas. It's only used for this
							search.
						</p>
						<Button size="sm" loading={locating} onclick={useMyLocation}>Use my location</Button>
					</div>
				{:else if nearby === null}
					<div class="grid grid-cols-2 gap-3">
						{#each [0, 1, 2, 3] as n (n)}<Skeleton class="h-28 rounded-card" />{/each}
					</div>
				{:else if nearby.length === 0}
					<p class="rounded-card border border-line bg-surface p-5 text-sm text-fg-muted">
						No salons within {NEAR_RADIUS_KM} km of you yet.
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
				<div class="mb-4 flex items-center justify-between gap-3">
					<h2
						id="top-heading"
						class="flex items-center gap-2 text-base font-semibold tracking-tight text-fg"
					>
						<Icon name="star" class="size-4 text-amber-500" />
						Top rated
					</h2>
					{#if topRated.length > 0}
						<Button size="sm" variant="ghost" onclick={() => changeSort('rating')}>
							See all
							<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
						</Button>
					{/if}
				</div>
				{#if topRated.length === 0}
					<p class="rounded-card border border-line bg-surface p-5 text-sm text-fg-muted">
						Ratings appear here once customers rate their visits.
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

	<!-- Result bar -->
	<div class="mb-6 flex flex-wrap items-center justify-between gap-3">
		<div class="flex items-center gap-3">
			<p class="text-sm text-fg-secondary" aria-live="polite">
				{#if loading}
					Searching…
				{:else}
					<span class="font-semibold text-fg tabular-nums">{listings.length}</span>
					{listings.length === 1 ? 'salon' : 'salons'}
					{#if selectedCity}in <span class="font-medium text-fg">{selectedCity}</span>{/if}
				{/if}
			</p>
			{#if q || selectedCity || selectedCategory || area}
				<Button size="sm" variant="ghost" onclick={resetFilters}>
					<Icon name="x" class="size-3.5" />
					Clear filters
				</Button>
			{/if}
		</div>

		<div class="flex items-center gap-2">
			<!-- Below `lg` the list and the map take turns. -->
			<div
				class="inline-flex rounded-control bg-surface-muted p-1 lg:hidden"
				role="group"
				aria-label="Show results as"
			>
				{#each views as mode (mode)}
					<button
						type="button"
						onclick={() => (view = mode)}
						aria-pressed={view === mode}
						class={[
							'h-7 rounded-[calc(var(--radius-control)-2px)] px-3 text-xs font-medium capitalize focus-ring transition-colors',
							view === mode
								? 'bg-surface text-fg shadow-card ring-1 ring-line'
								: 'text-fg-muted hover:text-fg'
						]}
					>
						{mode}
					</button>
				{/each}
			</div>
			<label for="sort-select" class="sr-only">Sort by</label>
			<select
				id="sort-select"
				value={sortBy}
				onchange={(event) => changeSort(event.currentTarget.value)}
				class={`${fieldBase} ${fieldBorder(false)} h-9 w-auto pe-9 text-[13px]`}
			>
				<option value="recommended">Recommended</option>
				<option value="rating">Top rated</option>
				<option value="nearest">Nearest to me</option>
				<option value="price-low">Price: low to high</option>
				<option value="price-high">Price: high to low</option>
			</select>
		</div>
	</div>

	<div
		class="lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)] lg:items-start lg:gap-8 xl:grid-cols-[minmax(0,1fr)_minmax(0,30rem)]"
	>
		<div class={[view === 'map' && 'hidden', 'lg:block']}>
			{#if loading}
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
					{#each [0, 1, 2, 3] as n (n)}
						<div class="space-y-3 rounded-card border border-line bg-surface p-5 shadow-card">
							<Skeleton class="h-5 w-2/3" />
							<Skeleton class="h-3 w-1/3" />
							<Skeleton class="h-3 w-full" />
							<Skeleton class="mt-6 h-9 w-full rounded-control" />
						</div>
					{/each}
				</div>
			{:else if listings.length === 0}
				<EmptyState
					title="No salons match"
					description="Try a different search term, category or city."
				>
					{#snippet icon()}<Icon name="search" class="size-6" />{/snippet}
					{#snippet action()}
						<Button variant="outline" onclick={resetFilters}>Reset filters</Button>
					{/snippet}
				</EmptyState>
			{:else}
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
					{#each listings as listing (listing.business_id + listing.location_id)}
						<article
							class="group flex flex-col rounded-card border border-line bg-surface shadow-card transition-[border-color,box-shadow,transform] duration-base ease-out-premium hover:-translate-y-0.5 hover:border-line-strong hover:shadow-raised"
						>
							{@render cover(listing, 'aspect-[16/9] rounded-t-card')}
							<div class="flex-1 p-5">
								<div class="flex items-start justify-between gap-3">
									<div class="min-w-0">
										<h3 class="font-semibold text-fg transition-colors group-hover:text-accent">
											{pickBilingual(listing, 'name', 'en')}
										</h3>
										{#if listing.name_ar}
											<p class="mt-0.5 w-fit text-xs text-fg-muted" dir="rtl" lang="ar">
												{listing.name_ar}
											</p>
										{/if}
									</div>
									<Badge tone="neutral" size="sm">{listing.city || 'KSA'}</Badge>
								</div>

								<div class="mt-2">
									<RatingStars
										average={listing.rating_average}
										count={listing.rating_count}
										size="sm"
									/>
								</div>

								<p class="mt-2 flex items-center gap-1.5 text-xs text-fg-muted">
									<Icon name="map-pin" class="size-3.5" />
									<span class="truncate">{listing.location_name_en || listing.city}</span>
									{#if listing.distance_km != null}
										<span aria-hidden="true">·</span>
										<span class="shrink-0">{listing.distance_km} km</span>
									{/if}
								</p>

								{#if listing.description_en}
									<p class="mt-3 line-clamp-2 text-sm text-fg-muted">{listing.description_en}</p>
								{/if}
							</div>

							<!-- Stacked rather than one row: next to the map a card can be under
							     280px wide, too narrow for a price and two buttons side by side. -->
							<div
								class="flex flex-col gap-3 rounded-b-card border-t border-line-subtle bg-surface-sunken px-5 py-4"
							>
								<p class="flex items-baseline justify-between gap-2 text-xs text-fg-muted">
									From
									<span class="text-base font-semibold text-fg tabular-nums">
										{formatMoney(listing.starting_price, listing.currency ?? 'SAR', 'en')}
									</span>
								</p>
								<div class="grid grid-cols-2 gap-2">
									<Button
										size="sm"
										variant="outline"
										fullWidth
										onclick={() => (quickViewSalon = listing)}
									>
										Quick View
									</Button>
									<Button
										href={resolve('/discover/[slug]', { slug: listing.slug })}
										size="sm"
										fullWidth
									>
										Book Now
									</Button>
								</div>
							</div>
						</article>
					{/each}
				</div>

				<div class="mt-10">
					<Pagination
						{limit}
						{offset}
						itemCount={listings.length}
						onchange={(next) => (offset = next)}
					/>
				</div>
			{/if}
		</div>

		<div class={[view === 'list' && 'hidden', 'lg:sticky lg:top-24 lg:block']}>
			<ListingsMap
				listings={pins}
				fit={area === null}
				loading={pinsLoading}
				truncated={pinsTruncated}
				areaActive={area !== null}
				onselect={(listing) => (quickViewSalon = listing)}
				onsearcharea={searchArea}
				onclear={() => searchArea(null)}
				class="h-[65vh] min-h-96 lg:h-[calc(100vh-8rem)]"
			/>
		</div>
	</div>
</Container>

<Modal
	open={quickViewSalon !== null}
	title={quickViewSalon?.name_en ?? ''}
	description={quickViewSalon?.name_ar ?? null}
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
		{#if quickViewSalon.description_en}
			<p class="text-sm text-fg-secondary">{quickViewSalon.description_en}</p>
		{/if}
		<dl class="mt-5 divide-y divide-line-subtle rounded-card border border-line text-sm">
			<div class="flex items-center gap-3 px-4 py-3">
				<Icon name="map-pin" class="size-4 text-accent" />
				<dt class="sr-only">Location</dt>
				<dd class="text-fg-secondary">
					{[quickViewSalon.location_name_en, quickViewSalon.city].filter(Boolean).join(', ')}
				</dd>
			</div>
			<div class="flex items-center gap-3 px-4 py-3">
				<Icon name="credit-card" class="size-4 text-accent" />
				<dt class="sr-only">Payment</dt>
				<dd class="text-fg-secondary">Mada, Apple Pay, Visa &amp; Mastercard</dd>
			</div>
			<div class="flex items-center gap-3 px-4 py-3">
				<Icon name="sparkles" class="size-4 text-accent" />
				<dt class="sr-only">Price</dt>
				<dd class="text-fg-secondary">
					Treatments from
					<span class="font-semibold text-fg tabular-nums">
						{formatMoney(quickViewSalon.starting_price, quickViewSalon.currency ?? 'SAR', 'en')}
					</span>
				</dd>
			</div>
		</dl>
	{/if}
	{#snippet footer()}
		<Button variant="ghost" onclick={() => (quickViewSalon = null)}>Close</Button>
		{#if quickViewSalon}
			<Button href={resolve('/discover/[slug]', { slug: quickViewSalon.slug })}>
				View Full Menu
			</Button>
		{/if}
	{/snippet}
</Modal>
