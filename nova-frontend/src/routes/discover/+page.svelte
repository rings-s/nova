<script>
	import { searchBusinesses } from '$lib/api/discovery.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { pickBilingual } from '$lib/utils/bilingual.js';
	import { formatMoney } from '$lib/utils/money.js';
	import { resolve } from '$app/paths';
	import Container from '$lib/components/marketing/Container.svelte';
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import Pagination from '$lib/components/ui/Pagination.svelte';

	let q = $state('');
	let selectedCity = $state('');
	let selectedCategory = $state('');
	let sortBy = $state('recommended');
	let offset = $state(0);
	const limit = 12;

	let loading = $state(true);
	let listings = $state(/** @type {any[]} */ ([]));

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

	async function search() {
		loading = true;
		try {
			const combinedQ = [q, selectedCategory].filter(Boolean).join(' ');
			const page = await searchBusinesses({
				q: combinedQ || null,
				city: selectedCity || null,
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

	$effect(() => {
		offset;
		selectedCity;
		selectedCategory;
		sortBy;
		search();
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
		offset = 0;
		search();
	}
</script>

<svelte:head>
	<title>Discover Salons &amp; Spas in Saudi Arabia &amp; GCC — NOVA</title>
	<meta
		name="description"
		content="Search beauty salons, spas, and hammams in Riyadh, Jeddah, and Al Khobar, and book directly with live availability."
	/>
</svelte:head>

<div class="min-h-screen bg-slate-50/50 pb-20 dark:bg-slate-950">
	<!-- Advanced Hero & Telemetry Header -->
	<section
		class="relative overflow-hidden border-b border-slate-200 bg-white py-10 sm:py-16 dark:border-slate-800 dark:bg-slate-900"
	>
		<GradientBlob variant="hero" />

		<Container size="lg" class="relative z-10">
			<!-- Telemetry Ribbon -->
			<div class="flex items-center justify-center">
				<div
					class="inline-flex flex-wrap items-center justify-center gap-2 rounded-full border border-slate-200/80 bg-white/90 px-4 py-1.5 text-xs font-semibold text-slate-700 shadow-xs backdrop-blur dark:border-slate-800/80 dark:bg-slate-900/90 dark:text-slate-300"
				>
					<span class="flex items-center gap-1.5">
						<span class="size-2 animate-pulse rounded-full bg-emerald-500"></span>
						<span class="font-mono font-bold text-slate-900 dark:text-slate-100">Live Slots</span>
					</span>
					<span class="text-slate-300 dark:text-slate-700">·</span>
					<span>Riyadh, Jeddah &amp; Khobar</span>
					<span class="text-slate-300 dark:text-slate-700">·</span>
					<span class="font-bold text-brand-600 dark:text-brand-400">Zero App Download</span>
					<span class="text-slate-300 dark:text-slate-700">·</span>
					<span class="font-bold text-emerald-700 dark:text-emerald-400">Moyasar Direct</span>
				</div>
			</div>

			<div class="mx-auto mt-6 max-w-3xl text-center">
				<h1
					class="text-display-lg font-extrabold tracking-tight text-slate-900 sm:text-display-xl dark:text-slate-100"
				>
					Discover premier salons &amp; spas
				</h1>
				<p class="mt-3 text-body-lg text-slate-600 dark:text-slate-400">
					Real-time slot holds, direct local bookings, and instant WhatsApp confirmations.
				</p>
			</div>

			<!-- Main Search Bar Form -->
			<form
				onsubmit={handleSubmit}
				class="mx-auto mt-8 max-w-3xl rounded-3xl border border-slate-200 bg-white/95 p-2.5 shadow-xl backdrop-blur dark:border-slate-800 dark:bg-slate-900/95"
			>
				<div class="flex flex-col gap-2 sm:flex-row sm:items-center">
					<div class="relative flex-1">
						<Icon
							name="search"
							class="absolute start-3.5 top-1/2 size-4 -translate-y-1/2 text-slate-400"
						/>
						<input
							type="text"
							placeholder="Search by salon name, service (e.g. HydraFacial, Balayage, Hammam)..."
							bind:value={q}
							class="w-full rounded-2xl bg-transparent py-2.5 ps-10 pe-3 text-sm text-slate-900 placeholder:text-slate-400 focus:ring-2 focus:ring-brand-500/20 focus:outline-none dark:text-slate-100"
						/>
					</div>
					<div class="hidden h-6 w-px bg-slate-200 sm:block dark:bg-slate-800"></div>
					<div class="sm:w-48">
						<select
							bind:value={selectedCity}
							class="w-full rounded-2xl border-0 bg-transparent px-3 py-2.5 text-sm text-slate-700 focus:outline-none dark:bg-slate-900 dark:text-slate-200"
						>
							{#each cities as c (c.id)}
								<option value={c.id}>{c.name}</option>
							{/each}
						</select>
					</div>
					<button
						type="submit"
						class="rounded-2xl bg-slate-900 px-6 py-2.5 text-sm font-semibold text-white shadow-xs transition-colors hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200"
					>
						Search
					</button>
				</div>
			</form>

			<!-- Category Quick Filters -->
			<div class="mt-6 flex flex-wrap items-center justify-center gap-2">
				{#each categories as cat (cat.id)}
					<button
						type="button"
						onclick={() => {
							selectedCategory = cat.id;
							offset = 0;
						}}
						class={[
							'inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-semibold transition-all',
							selectedCategory === cat.id
								? 'bg-slate-900 text-white shadow-sm dark:bg-slate-100 dark:text-slate-900'
								: 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
						].join(' ')}
					>
						<Icon name={cat.icon} class="size-3.5" />
						<span>{cat.name}</span>
					</button>
				{/each}
			</div>
		</Container>
	</section>

	<!-- Results List Section -->
	<Container size="lg" class="py-8 sm:py-12">
		<!-- Bar with count and sorting -->
		<div
			class="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-4 dark:border-slate-800"
		>
			<div class="flex items-center gap-2">
				<p class="text-sm font-medium text-slate-700 dark:text-slate-300">
					{#if loading}
						Searching available salons...
					{:else}
						Found <span class="font-bold text-slate-900 dark:text-slate-100">{listings.length}</span
						>
						salons
						{#if selectedCity}
							in <span class="font-semibold">{selectedCity}</span>
						{/if}
					{/if}
				</p>
				{#if q || selectedCity || selectedCategory}
					<button
						type="button"
						onclick={resetFilters}
						class="ms-2 text-xs font-semibold text-brand-600 hover:underline dark:text-brand-400"
					>
						Clear filters
					</button>
				{/if}
			</div>

			<div class="flex items-center gap-2 text-xs">
				<label for="sort-select" class="text-slate-500 dark:text-slate-400">Sort by:</label>
				<select
					id="sort-select"
					bind:value={sortBy}
					class="rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-xs dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
				>
					<option value="recommended">Recommended</option>
					<option value="price-low">Price: Low to High</option>
					<option value="price-high">Price: High to Low</option>
				</select>
			</div>
		</div>

		{#if loading}
			<div class="flex flex-col items-center justify-center py-20">
				<Spinner size="lg" />
				<p class="mt-4 font-mono text-xs text-slate-500">Searching salons in the GCC...</p>
			</div>
		{:else if listings.length === 0}
			<div
				class="rounded-3xl border border-slate-200 bg-white p-12 text-center shadow-xs dark:border-slate-800 dark:bg-slate-900"
			>
				<div
					class="mx-auto flex size-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-400 dark:bg-slate-800"
				>
					<Icon name="search" class="size-6" />
				</div>
				<h3 class="mt-4 text-lg font-bold text-slate-900 dark:text-slate-100">
					No salons matched your criteria
				</h3>
				<p class="mx-auto mt-1 max-w-md text-xs text-slate-500 dark:text-slate-400">
					Try clearing your search term or choosing a different city.
				</p>
				<div class="mt-6">
					<Button variant="outline" onclick={resetFilters}>Reset all filters</Button>
				</div>
			</div>
		{:else}
			<div class="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
				{#each listings as listing (listing.business_id + listing.location_id)}
					<div
						class="group flex flex-col justify-between overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-xs transition-all hover:-translate-y-1 hover:border-slate-300 hover:shadow-lg dark:border-slate-800 dark:bg-slate-900"
					>
						<div>
							<!-- Salon Content Body -->
							<div class="p-5">
								<div class="flex items-start justify-between gap-2">
									<div>
										<h3
											class="text-base font-bold text-slate-900 transition-colors group-hover:text-brand-600 dark:text-slate-100 dark:group-hover:text-brand-400"
										>
											{pickBilingual(listing, 'name', 'en')}
										</h3>
										{#if listing.name_ar}
											<p class="font-sans text-xs text-slate-500 dark:text-slate-400" dir="rtl">
												{listing.name_ar}
											</p>
										{/if}
									</div>
									<Badge tone="neutral" size="sm">
										{listing.city || 'KSA'}
									</Badge>
								</div>

								<div
									class="mt-2 flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400"
								>
									<Icon name="map-pin" class="size-3.5 shrink-0 text-slate-400" />
									<span>{listing.location_name_en || listing.city}</span>
									{#if listing.distance_km != null}
										<span>·</span>
										<span>{listing.distance_km} km away</span>
									{/if}
								</div>

								{#if listing.description_en}
									<p
										class="mt-3 line-clamp-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400"
									>
										{listing.description_en}
									</p>
								{/if}
							</div>
						</div>

						<!-- Card Footer with Price & Actions -->
						<div class="border-t border-slate-100 p-5 pt-4 dark:border-slate-800">
							<div class="mb-4 flex items-baseline justify-between">
								<span class="text-xs text-slate-400">Starting from</span>
								<span class="text-base font-extrabold text-slate-900 dark:text-slate-100">
									{formatMoney(listing.starting_price, listing.currency ?? 'SAR', 'en')}
								</span>
							</div>

							<div class="grid grid-cols-2 gap-2">
								<button
									type="button"
									onclick={() => (quickViewSalon = listing)}
									class="rounded-xl border border-slate-200 bg-white py-2 text-center text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
								>
									Quick View
								</button>
								<Button
									href={resolve('/discover/[slug]', { slug: listing.slug })}
									variant="primary"
									size="sm"
								>
									Book Now
								</Button>
							</div>
						</div>
					</div>
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
	</Container>

	<!-- Quick View Modal -->
	{#if quickViewSalon}
		<div
			class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
		>
			<div
				class="relative w-full max-w-lg rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl dark:border-slate-800 dark:bg-slate-900"
			>
				<button
					type="button"
					onclick={() => (quickViewSalon = null)}
					class="absolute end-5 top-5 inline-flex size-8 items-center justify-center rounded-full bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400"
					aria-label="Close"
				>
					<Icon name="x" class="size-4" />
				</button>

				<h3 class="mt-1 text-xl font-bold text-slate-900 dark:text-slate-100">
					{quickViewSalon.name_en}
				</h3>
				{#if quickViewSalon.name_ar}
					<p class="text-xs text-slate-500" dir="rtl">{quickViewSalon.name_ar}</p>
				{/if}

				{#if quickViewSalon.description_en}
					<p class="mt-3 text-xs leading-relaxed text-slate-600 dark:text-slate-300">
						{quickViewSalon.description_en}
					</p>
				{/if}

				<div class="mt-5 space-y-2 rounded-2xl bg-slate-50 p-4 text-xs dark:bg-slate-800/50">
					<div class="flex items-center gap-2 text-slate-700 dark:text-slate-300">
						<Icon name="map-pin" class="size-4 shrink-0 text-brand-600" />
						<span
							>{quickViewSalon.location_name_en || quickViewSalon.city}, {quickViewSalon.city}</span
						>
					</div>
					<div class="flex items-center gap-2 text-slate-700 dark:text-slate-300">
						<Icon name="credit-card" class="size-4 shrink-0 text-brand-600" />
						<span>Mada, Apple Pay, Visa &amp; Mastercard accepted via Moyasar</span>
					</div>
				</div>

				<div
					class="mt-6 flex items-center justify-between border-t border-slate-100 pt-4 dark:border-slate-800"
				>
					<div>
						<p class="text-[11px] text-slate-400">Treatments starting from</p>
						<p class="text-lg font-bold text-slate-900 dark:text-slate-100">
							{formatMoney(quickViewSalon.starting_price, quickViewSalon.currency ?? 'SAR', 'en')}
						</p>
					</div>

					<div class="flex gap-2">
						<Button variant="outline" size="sm" onclick={() => (quickViewSalon = null)}
							>Close</Button
						>
						<Button
							href={resolve('/discover/[slug]', { slug: quickViewSalon.slug })}
							variant="primary"
							size="sm"
						>
							View Full Menu
						</Button>
					</div>
				</div>
			</div>
		</div>
	{/if}
</div>
