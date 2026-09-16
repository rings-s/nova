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

	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import BookingCard from '$lib/components/booking/BookingCard.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	$effect(() => {
		if (!authStore.isAuthenticated) goto(resolve('/login'));
	});

	/** @typedef {{ tenantId: string, businessName: string, booking: import('$lib/api/booking.js').Booking }} Row */

	let loading = $state(true);
	let rows = $state(/** @type {Row[]} */ ([]));
	let cancellingId = $state(/** @type {string|null} */ (null));

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
</script>

<svelte:head><title>My bookings — NOVA</title></svelte:head>

<div class="mx-auto max-w-3xl px-4 py-8 sm:px-6">
	<PageHeader title="My bookings" />

	{#if loading}
		<div class="flex justify-center py-12"><Spinner /></div>
	{:else if rows.length === 0}
		<EmptyState
			title="No bookings yet"
			description="Find a salon on the marketplace to get started."
		>
			{#snippet action()}
				<Button href={resolve('/discover')}>Browse salons</Button>
			{/snippet}
		</EmptyState>
	{:else}
		<div class="flex flex-col gap-3">
			{#each rows as row (row.booking.id)}
				<div>
					<p class="mb-1 text-xs font-medium text-slate-500 dark:text-slate-400">
						{row.businessName}
					</p>
					<BookingCard booking={row.booking}>
						{#snippet actions()}
							{#if row.booking.status === 'confirmed' || row.booking.status === 'pending_payment'}
								<Button
									size="sm"
									variant="outline"
									loading={cancellingId === row.booking.id}
									onclick={() => handleCancel(row)}
								>
									Cancel
								</Button>
							{/if}
						{/snippet}
					</BookingCard>
				</div>
			{/each}
		</div>
	{/if}
</div>
