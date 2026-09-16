<script>
	/**
	 * The day sheet: one provider's appointments for one day, and the
	 * check-in → in-service → complete lifecycle staff drive by hand.
	 * `listProviderCalendar` (booking.js) is staff-only and scoped to one
	 * provider — there is no "every booking today" endpoint, so a location and
	 * provider must be chosen first, same as Catalog.
	 */
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { businessStore } from '$lib/stores/business.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { errorMessage } from '$lib/utils/errors.js';
	import { pickBilingual } from '$lib/utils/bilingual.js';
	import { formatDate } from '$lib/utils/datetime.js';
	import { listLocations, listProviders } from '$lib/api/catalog.js';
	import {
		listProviderCalendar,
		confirmBooking,
		cancelBooking,
		rescheduleBooking,
		checkInBooking,
		startBookingService,
		completeBooking,
		markBookingNoShow
	} from '$lib/api/booking.js';

	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import BookingCard from '$lib/components/booking/BookingCard.svelte';
	import SlotPicker from '$lib/components/booking/SlotPicker.svelte';

	let tenantId = $derived(/** @type {string} */ (tenantStore.activeTenantId));
	let businessId = $derived(businessStore.activeBusinessId);

	let locations = $state(/** @type {import('$lib/api/catalog.js').Location[]} */ ([]));
	let providers = $state(/** @type {import('$lib/api/catalog.js').Provider[]} */ ([]));
	let selectedLocationId = $state(/** @type {string} */ (''));
	let selectedProviderId = $state(/** @type {string} */ (''));
	let selectedDate = $state(new Date().toISOString().slice(0, 10));

	let loadingSetup = $state(true);
	let setupErrorMessage = $state(/** @type {string|null} */ (null));

	async function loadSetup() {
		const currentBusinessId = businessId;
		if (!currentBusinessId) return;
		loadingSetup = true;
		setupErrorMessage = null;
		try {
			const page = await listLocations(tenantId, currentBusinessId);
			locations = page.items;
			if (!selectedLocationId && locations[0]) selectedLocationId = locations[0].id;
		} catch (err) {
			setupErrorMessage = errorMessage(err);
		} finally {
			loadingSetup = false;
		}
	}

	$effect(() => {
		if (businessId) loadSetup();
	});

	async function loadProviders() {
		const currentLocationId = selectedLocationId;
		if (!currentLocationId) {
			providers = [];
			return;
		}
		try {
			const page = await listProviders(tenantId, currentLocationId);
			providers = page.items;
			if (!providers.some((p) => p.id === selectedProviderId)) {
				selectedProviderId = providers[0]?.id ?? '';
			}
		} catch (err) {
			toastStore.fromError(err);
		}
	}

	$effect(() => {
		if (selectedLocationId) loadProviders();
	});

	let loading = $state(false);
	let loadErrorMessage = $state(/** @type {string|null} */ (null));
	let bookings = $state(/** @type {import('$lib/api/booking.js').Booking[]} */ ([]));

	/** Day's ISO bounds in the viewer's own clock — a day sheet is read by
	 * whoever is physically at the front desk, so their local midnight is the
	 * right boundary. */
	let dayRange = $derived.by(() => {
		const start = new Date(`${selectedDate}T00:00:00`);
		const end = new Date(start.getTime() + 24 * 60 * 60 * 1000);
		return { dateFrom: start.toISOString(), dateTo: end.toISOString() };
	});

	async function loadDaySheet() {
		const providerId = selectedProviderId;
		if (!providerId) {
			bookings = [];
			return;
		}
		loading = true;
		loadErrorMessage = null;
		try {
			const page = await listProviderCalendar(tenantId, providerId, dayRange);
			bookings = [...page.items].sort(
				(a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime()
			);
		} catch (err) {
			loadErrorMessage = errorMessage(err);
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (selectedProviderId) loadDaySheet();
	});

	/** @param {number} deltaDays */
	function shiftDay(deltaDays) {
		// A local, one-shot scratchpad — never stored in state, so it doesn't
		// need to be reactive.
		// eslint-disable-next-line svelte/prefer-svelte-reactivity
		const next = new Date(`${selectedDate}T00:00:00`);
		next.setDate(next.getDate() + deltaDays);
		selectedDate = next.toISOString().slice(0, 10);
	}

	/** @param {import('$lib/api/booking.js').Booking} updated */
	function applyUpdate(updated) {
		bookings = bookings.map((b) => (b.id === updated.id ? updated : b));
	}

	let actingId = $state(/** @type {string|null} */ (null));

	/** @param {import('$lib/api/booking.js').Booking} booking @param {() => Promise<import('$lib/api/booking.js').Booking>} action */
	async function runAction(booking, action) {
		actingId = booking.id;
		try {
			applyUpdate(await action());
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			actingId = null;
		}
	}

	// --- Reschedule ----------------------------------------------------------------

	let rescheduleTarget = $state(/** @type {import('$lib/api/booking.js').Booking|null} */ (null));
	let rescheduling = $state(false);

	/** @param {import('$lib/api/booking.js').AvailableSlot|import('$lib/api/discovery.js').PublicSlot} slot */
	async function handleRescheduleSelect(slot) {
		const target = rescheduleTarget;
		if (!target) return;
		rescheduling = true;
		try {
			const updated = await rescheduleBooking(tenantId, target.id, {
				newStartsAt: slot.starts_at,
				providerId: slot.provider_id
			});
			// The booking may have moved to a different day than the one on screen.
			bookings = bookings.filter((b) => b.id !== updated.id);
			if (updated.provider_id === selectedProviderId) {
				const startsOnScreenDay =
					updated.starts_at >= dayRange.dateFrom && updated.starts_at < dayRange.dateTo;
				if (startsOnScreenDay) bookings = [...bookings, updated];
			}
			rescheduleTarget = null;
			toastStore.success('Booking rescheduled.');
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			rescheduling = false;
		}
	}

	let rescheduleRange = $derived.by(() => {
		const now = new Date();
		return {
			dateFrom: now.toISOString(),
			dateTo: new Date(now.getTime() + 14 * 24 * 60 * 60 * 1000).toISOString()
		};
	});
</script>

<svelte:head><title>Bookings — NOVA</title></svelte:head>

<PageHeader title="Bookings" subtitle="One provider's day sheet." />

{#if !businessId}
	<Alert tone="info">Set up your storefront in Catalog first.</Alert>
{:else if loadingSetup}
	<div class="flex justify-center py-12"><Spinner /></div>
{:else if setupErrorMessage}
	<Alert tone="error">{setupErrorMessage}</Alert>
{:else if locations.length === 0}
	<EmptyState title="Add a location first" description="Bookings belong to one branch." />
{:else}
	<div class="mb-4 flex flex-wrap items-end gap-3">
		<div class="w-full max-w-xs">
			<Select
				label="Location"
				bind:value={selectedLocationId}
				options={locations.map((l) => ({ value: l.id, label: pickBilingual(l, 'name', 'en') }))}
			/>
		</div>
		<div class="w-full max-w-xs">
			<Select
				label="Provider"
				disabled={providers.length === 0}
				bind:value={selectedProviderId}
				placeholder={providers.length === 0 ? 'No providers at this location' : null}
				options={providers.map((p) => ({ value: p.id, label: pickBilingual(p, 'name', 'en') }))}
			/>
		</div>
		<div class="flex items-end gap-1">
			<Button variant="outline" size="md" onclick={() => shiftDay(-1)} aria-label="Previous day">
				←
			</Button>
			<input
				type="date"
				bind:value={selectedDate}
				class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
			/>
			<Button variant="outline" size="md" onclick={() => shiftDay(1)} aria-label="Next day">
				→
			</Button>
		</div>
	</div>

	{#if !selectedProviderId}
		<EmptyState title="Add a provider first" description="The day sheet is per provider." />
	{:else if loading}
		<div class="flex justify-center py-12"><Spinner /></div>
	{:else if loadErrorMessage}
		<Alert tone="error">{loadErrorMessage}</Alert>
	{:else if bookings.length === 0}
		<EmptyState title="Nothing booked" description={formatDate(selectedDate, 'en')} />
	{:else}
		<div class="flex flex-col gap-3">
			{#each bookings as booking (booking.id)}
				<BookingCard {booking}>
					{#snippet actions()}
						{#if booking.status === 'draft' || booking.status === 'pending_payment'}
							<Button
								size="sm"
								loading={actingId === booking.id}
								onclick={() => runAction(booking, () => confirmBooking(tenantId, booking.id))}
							>
								Confirm
							</Button>
						{/if}
						{#if booking.status === 'confirmed'}
							<Button
								size="sm"
								loading={actingId === booking.id}
								onclick={() => runAction(booking, () => checkInBooking(tenantId, booking.id))}
							>
								Check in
							</Button>
							<Button
								size="sm"
								variant="outline"
								loading={actingId === booking.id}
								onclick={() => runAction(booking, () => markBookingNoShow(tenantId, booking.id))}
							>
								No-show
							</Button>
						{/if}
						{#if booking.status === 'checked_in'}
							<Button
								size="sm"
								loading={actingId === booking.id}
								onclick={() => runAction(booking, () => startBookingService(tenantId, booking.id))}
							>
								Start service
							</Button>
						{/if}
						{#if booking.status === 'in_service'}
							<Button
								size="sm"
								loading={actingId === booking.id}
								onclick={() => runAction(booking, () => completeBooking(tenantId, booking.id))}
							>
								Complete
							</Button>
						{/if}
						{#if ['draft', 'pending_payment', 'confirmed'].includes(booking.status)}
							<Button size="sm" variant="outline" onclick={() => (rescheduleTarget = booking)}>
								Reschedule
							</Button>
							<Button
								size="sm"
								variant="danger"
								loading={actingId === booking.id}
								onclick={() =>
									runAction(booking, () => cancelBooking(tenantId, booking.id, { byStaff: true }))}
							>
								Cancel
							</Button>
						{/if}
					{/snippet}
				</BookingCard>
			{/each}
		</div>
	{/if}
{/if}

<Modal
	open={rescheduleTarget !== null}
	title="Reschedule"
	onclose={() => (rescheduleTarget = null)}
>
	{#if rescheduleTarget}
		{#if rescheduling}
			<div class="flex justify-center py-8"><Spinner /></div>
		{:else}
			<SlotPicker
				{tenantId}
				providerId={rescheduleTarget.provider_id}
				serviceId={rescheduleTarget.service_id}
				dateFrom={rescheduleRange.dateFrom}
				dateTo={rescheduleRange.dateTo}
				onselect={handleRescheduleSelect}
			/>
		{/if}
	{/if}
</Modal>
