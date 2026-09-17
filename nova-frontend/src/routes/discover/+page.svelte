<script>
	/**
	 * The marketplace's front door — public, unauthenticated (ADR-0010).
	 * `searchBusinesses` returns no `total` by design (discovery.js), so
	 * paging here is "keep the last page's size" rather than a page count.
	 */
	import { searchBusinesses } from '$lib/api/discovery.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { pickBilingual } from '$lib/utils/bilingual.js';
	import { formatMoney } from '$lib/utils/money.js';
	import { resolve } from '$app/paths';

	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import Container from '$lib/components/marketing/Container.svelte';

	let q = $state('');
	let city = $state('');
	let offset = $state(0);
	const limit = 12;

	let loading = $state(true);
	let listings = $state(/** @type {import('$lib/api/discovery.js').ListingCard[]} */ ([]));

	async function search() {
		loading = true;
		try {
			const page = await searchBusinesses({ q: q || null, city: city || null, limit, offset });
			listings = page.items;
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		offset;
		search();
	});

	/** @param {SubmitEvent} event */
	function handleSubmit(event) {
		event.preventDefault();
		offset = 0;
		search();
	}
</script>

<svelte:head><title>Find a salon — NOVA</title></svelte:head>

<Container size="lg" class="py-10 sm:py-14">
	<PageHeader title="Find a salon or spa" subtitle="Search the NOVA marketplace." />

	<form
		class="mb-8 flex flex-wrap gap-3 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900"
		onsubmit={handleSubmit}
	>
		<div class="min-w-0 flex-1">
			<Input placeholder="Search by name or service" bind:value={q} />
		</div>
		<div class="w-40">
			<Input placeholder="City" bind:value={city} />
		</div>
	</form>

	{#if loading}
		<div class="flex justify-center py-12"><Spinner /></div>
	{:else if listings.length === 0}
		<EmptyState title="No results" description="Try a different search or city." />
	{:else}
		<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
			{#each listings as listing (listing.business_id + listing.location_id)}
				<a href={resolve('/discover/[slug]', { slug: listing.slug })} class="block">
					<Card padding="md" class="h-full transition-shadow hover:shadow-md">
						<div class="flex items-start justify-between gap-2">
							<p class="font-medium text-slate-900 dark:text-slate-100">
								{pickBilingual(listing, 'name', 'en')}
							</p>
							{#if listing.city}
								<Badge tone="neutral" size="sm">{listing.city}</Badge>
							{/if}
						</div>
						<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">
							{listing.location_name_en}
						</p>
						{#if listing.starting_price}
							<p class="mt-3 text-sm font-medium text-brand-600 dark:text-brand-400">
								From {formatMoney(listing.starting_price, listing.currency ?? 'SAR', 'en')}
							</p>
						{/if}
					</Card>
				</a>
			{/each}
		</div>

		<div class="mt-6">
			<Pagination
				{limit}
				{offset}
				itemCount={listings.length}
				onchange={(next) => (offset = next)}
			/>
		</div>
	{/if}
</Container>
