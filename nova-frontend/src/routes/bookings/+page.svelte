<script>
	/**
	 * The customer's own bookings, aggregated across every tenant they've
	 * booked with on this browser (`customerTenantsStore` — see its own
	 * comment for why: there is no cross-tenant "my bookings" endpoint).
	 */
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { customerTenantsStore } from '$lib/stores/customerTenants.svelte.js';
	import { listBookings, cancelBooking } from '$lib/api/booking.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import BookingCard from '$lib/components/booking/BookingCard.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import StatCard from '$lib/components/ui/StatCard.svelte';
	import Tabs from '$lib/components/ui/Tabs.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Textarea from '$lib/components/ui/Textarea.svelte';
	import StarInput from '$lib/components/review/StarInput.svelte';
	import RatingStars from '$lib/components/review/RatingStars.svelte';
	import { listMyReviews, submitReview } from '$lib/api/review.js';

	$effect(() => {
		if (!authStore.isAuthenticated) {
			// eslint-disable-next-line svelte/no-navigation-without-resolve
			goto(`${resolve('/login')}?next=${encodeURIComponent('/bookings')}`, { replaceState: true });
		}
	});

	/** @typedef {{ tenantId: string, businessName: string, booking: import('$lib/api/booking.js').Booking }} Row */
	let loading = $state(true);
	let rows = $state(/** @type {Row[]} */ ([]));
	let cancellingId = $state(/** @type {string|null} */ (null));
	let activeTab = $state('all'); // 'all' | 'upcoming' | 'completed' | 'cancelled'

	/** Booking id → the star rating the customer gave it. */
	let ratings = $state(/** @type {Record<string, number>} */ ({}));
	let rateTarget = $state(/** @type {Row | null} */ (null));
	let rateValue = $state(0);
	let rateComment = $state('');
	let rating = $state(false);

	/** @param {Row} row */
	function openRate(row) {
		rateTarget = row;
		rateValue = 0;
		rateComment = '';
	}

	async function submitRating() {
		if (!rateTarget || rateValue < 1) return;
		rating = true;
		try {
			const review = await submitReview(rateTarget.tenantId, {
				bookingId: rateTarget.booking.id,
				rating: rateValue,
				comment: rateComment.trim() || null
			});
			ratings = { ...ratings, [review.booking_id]: review.rating };
			toastStore.success(`Thanks — you rated ${rateTarget.businessName} ${review.rating}/5.`);
			rateTarget = null;
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			rating = false;
		}
	}

	async function loadAll() {
		loading = true;
		try {
			const results = await Promise.all(
				customerTenantsStore.all.map(async (tenant) => {
					const result = await listBookings(tenant.tenantId, { limit: 50 });
					return result.items.map((booking) => ({
						tenantId: tenant.tenantId,
						businessName: tenant.businessName,
						booking
					}));
				})
			);
			// What has already been rated, so a finished visit shows its stars
			// instead of asking again. One call per salon the customer has used.
			const reviewed = await Promise.all(
				customerTenantsStore.all.map((tenant) => listMyReviews(tenant.tenantId).catch(() => []))
			);
			ratings = Object.fromEntries(
				reviewed.flat().map((review) => [review.booking_id, review.rating])
			);
			rows = results
				.flat()
				.sort(
					(a, b) =>
						new Date(b.booking.starts_at).getTime() - new Date(a.booking.starts_at).getTime()
				);
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (authStore.isAuthenticated) loadAll();
	});

	/** @param {Row} row */
	async function handleCancel(row) {
		if (!confirm('Are you sure you want to cancel this booking?')) return;
		cancellingId = row.booking.id;
		try {
			const updated = await cancelBooking(row.tenantId, row.booking.id);
			rows = rows.map((r) => (r.booking.id === updated.id ? { ...r, booking: updated } : r));
			toastStore.success('Booking cancelled.');
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			cancellingId = null;
		}
	}

	let upcomingCount = $derived(
		rows.filter((r) => r.booking.status === 'confirmed' || r.booking.status === 'pending_payment')
			.length
	);
	let completedCount = $derived(rows.filter((r) => r.booking.status === 'completed').length);
	let cancelledCount = $derived(
		rows.filter((r) => r.booking.status === 'cancelled' || r.booking.status === 'no_show').length
	);

	let filteredRows = $derived(
		rows.filter((r) => {
			if (activeTab === 'upcoming') {
				return r.booking.status === 'confirmed' || r.booking.status === 'pending_payment';
			}
			if (activeTab === 'completed') {
				return r.booking.status === 'completed';
			}
			if (activeTab === 'cancelled') {
				return r.booking.status === 'cancelled' || r.booking.status === 'no_show';
			}
			return true;
		})
	);
</script>

<svelte:head>
	<title>My bookings — NOVA</title>
</svelte:head>

<Container size="lg" class="py-10 sm:py-14">
	<PageHeader
		eyebrow="Your account"
		title="My bookings"
		subtitle="Every appointment you've made across NOVA salons and spas."
	>
		{#snippet actions()}
			<Button href={resolve('/discover')} variant="outline">
				<Icon name="search" class="size-4" />
				Find a salon
			</Button>
		{/snippet}
	</PageHeader>

	{#if loading}
		<div class="flex justify-center py-20"><Spinner size="lg" /></div>
	{:else if rows.length === 0}
		<EmptyState
			title="No bookings yet"
			description="Find a salon on the marketplace and book your first visit."
		>
			{#snippet icon()}<Icon name="calendar" class="size-6" />{/snippet}
			{#snippet action()}
				<Button href={resolve('/discover')}>Browse salons</Button>
			{/snippet}
		</EmptyState>
	{:else}
		<div class="mb-8 grid grid-cols-3 gap-3 sm:gap-4">
			<StatCard label="Upcoming" icon="calendar" value={upcomingCount} />
			<StatCard label="Completed" icon="check" value={completedCount} />
			<StatCard label="Cancelled" icon="x" value={cancelledCount} />
		</div>

		<div class="mb-5 flex flex-wrap items-center justify-between gap-3">
			<Tabs
				tabs={[
					{ id: 'all', label: 'All', count: rows.length },
					{ id: 'upcoming', label: 'Upcoming', count: upcomingCount },
					{ id: 'completed', label: 'Completed', count: completedCount },
					{ id: 'cancelled', label: 'Cancelled', count: cancelledCount }
				]}
				bind:active={activeTab}
			/>
		</div>

		{#if filteredRows.length === 0}
			<EmptyState title="Nothing here" description="No appointments match this filter." />
		{:else}
			<div class="flex flex-col gap-3">
				{#each filteredRows as row (row.booking.id)}
					<BookingCard booking={row.booking} title={row.businessName}>
						{#snippet actions()}
							{#if row.booking.status === 'completed'}
								{#if ratings[row.booking.id]}
									<span class="inline-flex items-center gap-2 text-xs text-fg-muted">
										You rated
										<RatingStars
											average={ratings[row.booking.id]}
											count={1}
											size="sm"
											showCount={false}
										/>
									</span>
								{:else}
									<Button size="sm" onclick={() => openRate(row)}>
										<Icon name="star" class="size-4" />
										Rate visit
									</Button>
								{/if}
							{/if}
							{#if row.booking.status === 'confirmed' || row.booking.status === 'pending_payment'}
								<Button
									size="sm"
									variant="danger-ghost"
									loading={cancellingId === row.booking.id}
									onclick={() => handleCancel(row)}
								>
									Cancel
								</Button>
							{/if}
							<Button size="sm" variant="outline" href={resolve('/discover')}>Book again</Button>
						{/snippet}
					</BookingCard>
				{/each}
			</div>
			<Alert tone="info" class="mt-6">
				Need to change a time or get directions? Reply to your WhatsApp confirmation message.
			</Alert>
		{/if}
	{/if}
</Container>

<Modal
	open={rateTarget !== null}
	title="Rate your visit"
	description={rateTarget?.businessName ?? null}
	size="sm"
	onclose={() => (rateTarget = null)}
>
	<form
		id="rate-form"
		class="flex flex-col gap-5"
		onsubmit={(event) => {
			event.preventDefault();
			submitRating();
		}}
	>
		<StarInput bind:value={rateValue} label="How was it?" />
		<Textarea
			label="Anything to add?"
			hint="Optional. Only the salon's staff see your comment; your stars count toward its public rating."
			rows={3}
			maxlength={1000}
			bind:value={rateComment}
		/>
	</form>
	{#snippet footer()}
		<Button variant="ghost" onclick={() => (rateTarget = null)}>Cancel</Button>
		<Button type="submit" form="rate-form" loading={rating} disabled={rateValue < 1}>
			Submit rating
		</Button>
	{/snippet}
</Modal>
