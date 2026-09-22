<script>
	/**
	 * What customers said about their visits. The stars are public (they rank
	 * the business on the marketplace); the comments are for staff only.
	 */
	import { resolve } from '$app/paths';
	import { businessStore } from '$lib/stores/business.svelte.js';
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { getBusiness } from '$lib/api/catalog.js';
	import { listBusinessReviews } from '$lib/api/review.js';
	import { errorMessage } from '$lib/utils/errors.js';
	import { formatDate } from '$lib/utils/datetime.js';

	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import RatingStars from '$lib/components/review/RatingStars.svelte';

	let businessId = $derived(businessStore.activeBusinessId);
	let tenantId = $derived(tenantStore.activeTenantId);

	const limit = 20;
	let offset = $state(0);
	let loading = $state(true);
	let loadError = $state(/** @type {string|null} */ (null));
	let business = $state(/** @type {import('$lib/api/catalog.js').Business|null} */ (null));
	let reviews = $state(/** @type {import('$lib/api/review.js').Review[]} */ ([]));

	$effect(() => {
		if (!tenantId || !businessId) {
			loading = false;
			return;
		}
		const tenant = tenantId;
		const biz = businessId;
		const page = offset;
		let cancelled = false;
		loading = true;
		loadError = null;
		Promise.all([
			getBusiness(tenant, biz),
			listBusinessReviews(tenant, biz, { limit, offset: page })
		])
			.then(([b, result]) => {
				if (cancelled) return;
				business = b;
				reviews = result.items;
			})
			.catch((err) => {
				if (!cancelled) loadError = errorMessage(err);
			})
			.finally(() => {
				if (!cancelled) loading = false;
			});
		return () => {
			cancelled = true;
		};
	});

	/** Share of each star value on this page of reviews, 5 down to 1. */
	let distribution = $derived(
		[5, 4, 3, 2, 1].map((stars) => {
			const n = reviews.filter((r) => r.rating === stars).length;
			return { stars, n, share: reviews.length ? n / reviews.length : 0 };
		})
	);
</script>

<svelte:head><title>Reviews — NOVA</title></svelte:head>

<PageHeader
	eyebrow="Business"
	title="Reviews"
	subtitle="Ratings from verified visits. Stars are public on the marketplace; comments are for your team only."
/>

{#if !businessId}
	<Alert tone="info">Set up your storefront in Catalog first.</Alert>
{:else if loadError}
	<Alert tone="error">{loadError}</Alert>
{:else if loading && !business}
	<div class="grid gap-6 lg:grid-cols-[18rem_minmax(0,1fr)]">
		<Skeleton class="h-56 rounded-card" />
		<div class="space-y-3">
			{#each [0, 1, 2] as n (n)}<Skeleton class="h-24 rounded-card" />{/each}
		</div>
	</div>
{:else}
	<div class="grid items-start gap-6 lg:grid-cols-[18rem_minmax(0,1fr)]">
		<Card padding="lg" class="lg:sticky lg:top-8">
			<p class="text-[13px] font-medium text-fg-muted">Overall rating</p>
			{#if business?.rating_average != null}
				<p class="mt-2 text-5xl font-semibold tracking-tight text-fg tabular-nums">
					{business.rating_average.toFixed(1)}
				</p>
				<div class="mt-2">
					<RatingStars average={business.rating_average} count={business.rating_count} />
				</div>
				{#if reviews.length > 0}
					<ul class="mt-6 space-y-1.5" aria-label="Ratings on this page by stars">
						{#each distribution as row (row.stars)}
							<li class="flex items-center gap-2 text-xs">
								<span class="w-3 text-end text-fg-muted tabular-nums">{row.stars}</span>
								<span class="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-muted">
									<span
										class="block h-full rounded-full bg-amber-400"
										style={`width: ${row.share * 100}%`}
									></span>
								</span>
								<span class="w-5 text-fg-muted tabular-nums">{row.n}</span>
							</li>
						{/each}
					</ul>
				{/if}
			{:else}
				<p class="mt-2 text-3xl font-semibold text-fg-subtle">—</p>
				<p class="mt-2 text-sm text-fg-muted">
					No ratings yet. Customers can rate a visit once it's marked completed.
				</p>
			{/if}
		</Card>

		<section aria-label="Reviews">
			{#if reviews.length === 0}
				<EmptyState
					title="No reviews yet"
					description="When customers rate their completed visits, their stars and comments appear here."
				>
					{#snippet icon()}<Icon name="star" class="size-6" />{/snippet}
				</EmptyState>
			{:else}
				<ul class="flex flex-col gap-3">
					{#each reviews as review (review.id)}
						<li class="rounded-card border border-line bg-surface p-5 shadow-card">
							<div class="flex flex-wrap items-center justify-between gap-2">
								<RatingStars average={review.rating} count={1} size="sm" showCount={false} />
								<span class="text-xs text-fg-muted">{formatDate(review.created_at, 'en')}</span>
							</div>
							{#if review.comment}
								<p class="mt-3 text-sm whitespace-pre-line text-fg-secondary">{review.comment}</p>
							{:else}
								<p class="mt-3 text-sm text-fg-subtle italic">No comment.</p>
							{/if}
							<a
								href={resolve('/app/customers/[id]', { id: review.customer_id })}
								class="mt-3 inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
							>
								View customer
								<Icon name="chevron-right" class="size-3.5 rtl:rotate-180" />
							</a>
						</li>
					{/each}
				</ul>
				<div class="mt-6">
					<Pagination
						{limit}
						{offset}
						itemCount={reviews.length}
						onchange={(next) => (offset = next)}
					/>
				</div>
			{/if}
		</section>
	</div>
{/if}
