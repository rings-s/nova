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
	import Badge from '$lib/components/ui/Badge.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import Section from '$lib/components/marketing/Section.svelte';

	$effect(() => {
		if (!authStore.isAuthenticated) goto(resolve('/login'));
	});

	/** @typedef {{ tenantId: string, businessName: string, booking: import('$lib/api/booking.js').Booking }} Row */
	let loading = $state(true);
	let rows = $state(/** @type {Row[]} */ ([]));
	let cancellingId = $state(/** @type {string|null} */ (null));
	let activeTab = $state('all'); // 'all' | 'upcoming' | 'completed' | 'cancelled'

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
		rows.filter((r) => r.booking.status === 'confirmed' || r.booking.status === 'pending_payment').length
	);
	let completedCount = $derived(
		rows.filter((r) => r.booking.status === 'completed').length
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
				return r.booking.status === 'cancelled';
			}
			return true;
		})
	);
</script>

<svelte:head>
	<title>My Bookings &amp; Appointments — NOVA</title>
</svelte:head>

<div class="min-h-[calc(100vh-60px)] bg-slate-50/60 pb-20 dark:bg-slate-950">
	<!-- Page Header Hero -->
	<section class="border-b border-slate-200 bg-white py-10 sm:py-12 dark:border-slate-800 dark:bg-slate-900">
		<Container size="lg">
			<div class="flex flex-wrap items-center justify-between gap-4">
				<div>
					<div class="flex items-center gap-2">
						<Badge tone="brand" size="sm">Client Portal</Badge>
						<span class="text-xs font-medium text-slate-500">
							{rows.length} total visit records
						</span>
					</div>
					<h1 class="mt-2 text-display-md font-bold tracking-tight text-slate-900 sm:text-display-lg dark:text-slate-100">
						My Salon Bookings
					</h1>
					<p class="mt-1 text-xs text-slate-600 dark:text-slate-400">
						Live status, deterministic slot holds, and automated WhatsApp reminders.
					</p>
				</div>

				<div class="flex items-center gap-2">
					<Button href={resolve('/discover')} variant="outline" size="md">
						<Icon name="search" class="size-4" />
						<span>Explore Salons</span>
					</Button>
				</div>
			</div>

			<!-- Quick Summary Counters -->
			<div class="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
				<div class="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-800/50">
					<span class="text-xs font-medium text-slate-500">Upcoming Active</span>
					<p class="mt-1 font-mono text-xl font-bold text-emerald-600 dark:text-emerald-400">
						{upcomingCount}
					</p>
				</div>
				<div class="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-800/50">
					<span class="text-xs font-medium text-slate-500">Completed Visits</span>
					<p class="mt-1 font-mono text-xl font-bold text-slate-900 dark:text-slate-100">
						{completedCount}
					</p>
				</div>
				<div class="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-800/50">
					<span class="text-xs font-medium text-slate-500">Moyasar Direct</span>
					<p class="mt-1 font-mono text-xl font-bold text-brand-600 dark:text-brand-400">
						Protected
					</p>
				</div>
				<div class="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-800/50">
					<span class="text-xs font-medium text-slate-500">WhatsApp Alert</span>
					<p class="mt-1 font-mono text-xl font-bold text-emerald-600 dark:text-emerald-400">
						Active
					</p>
				</div>
			</div>

			<!-- Filter Tabs -->
			<div class="mt-8 flex items-center gap-1 border-t border-slate-100 pt-4 dark:border-slate-800">
				{#each [
					{ id: 'all', label: `All (${rows.length})` },
					{ id: 'upcoming', label: `Upcoming (${upcomingCount})` },
					{ id: 'completed', label: `Completed (${completedCount})` },
					{ id: 'cancelled', label: 'Cancelled' }
				] as tab (tab.id)}
					<button
						type="button"
						onclick={() => (activeTab = tab.id)}
						class={[
							'rounded-xl px-3.5 py-1.5 text-xs font-semibold transition-all',
							activeTab === tab.id
								? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
								: 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800'
						].join(' ')}
					>
						{tab.label}
					</button>
				{/each}
			</div>
		</Container>
	</section>

	<!-- Content Section -->
	<Container size="lg" class="py-10">
		{#if loading}
			<div class="flex flex-col items-center justify-center py-20">
				<Spinner size="lg" />
				<p class="mt-4 text-xs text-slate-500 font-mono">Syncing customer day sheet across GCC salons...</p>
			</div>
		{:else if rows.length === 0}
			<div class="rounded-3xl border border-dashed border-slate-300 bg-white p-12 text-center shadow-xs dark:border-slate-800 dark:bg-slate-900">
				<div class="mx-auto flex size-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-950/60 dark:text-brand-400">
					<Icon name="calendar" class="size-6" />
				</div>
				<h3 class="mt-4 text-lg font-bold text-slate-900 dark:text-slate-100">
					No salon bookings yet
				</h3>
				<p class="mx-auto mt-2 max-w-sm text-xs text-slate-500 dark:text-slate-400">
					Discover premier salons in Riyadh, Jeddah, and Dubai with instant Apple Pay and zero wait times.
				</p>
				<div class="mt-6">
					<Button href={resolve('/discover')}>Browse marketplace salons</Button>
				</div>
			</div>
		{:else if filteredRows.length === 0}
			<div class="rounded-2xl border border-slate-200 bg-white p-8 text-center text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900">
				No appointments match the "{activeTab}" filter.
			</div>
		{:else}
			<div class="space-y-4">
				{#each filteredRows as row (row.booking.id)}
					<div class="rounded-3xl border border-slate-200 bg-white p-6 shadow-xs transition-all hover:border-slate-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-900">
						<div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3 dark:border-slate-800">
							<div class="flex items-center gap-2">
								<span class="rounded-lg bg-brand-50 px-2 py-0.5 text-xs font-bold text-brand-700 dark:bg-brand-950/60 dark:text-brand-300">
									{row.businessName}
								</span>
								<span class="text-xs text-slate-400 font-mono">
									#{row.booking.id.slice(0, 8)}
								</span>
							</div>

							<div class="flex items-center gap-2">
								<span
									class={[
										'rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase',
										row.booking.status === 'confirmed'
											? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
											: row.booking.status === 'pending_payment'
												? 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300'
												: row.booking.status === 'completed'
													? 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
													: 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300'
									].join(' ')}
								>
									{row.booking.status.replace('_', ' ')}
								</span>
							</div>
						</div>

						<div class="mt-4">
							<BookingCard booking={row.booking}>
								{#snippet actions()}
									<div class="flex items-center gap-2">
										{#if row.booking.status === 'confirmed' || row.booking.status === 'pending_payment'}
											<Button
												size="sm"
												variant="outline"
												loading={cancellingId === row.booking.id}
												onclick={() => handleCancel(row)}
											>
												Cancel Appointment
											</Button>
										{/if}
										<Button
											size="sm"
											variant="ghost"
											href={resolve('/discover')}
										>
											Rebook
										</Button>
									</div>
								{/snippet}
							</BookingCard>
						</div>

						<!-- WhatsApp Assistance Micro-Tip -->
						<div class="mt-4 flex items-center justify-between rounded-xl bg-slate-50 px-4 py-2 text-[11px] text-slate-500 dark:bg-slate-800/50 dark:text-slate-400">
							<span class="flex items-center gap-1.5">
								<span class="size-2 rounded-full bg-emerald-500"></span>
								<span>Need to modify time or directions? Reply directly to your WhatsApp confirmation message.</span>
							</span>
							<span class="font-mono text-emerald-600 dark:text-emerald-400 font-semibold">
								Moyasar Protected
							</span>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</Container>
</div>
