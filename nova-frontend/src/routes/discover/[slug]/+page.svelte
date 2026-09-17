<script>
	/**
	 * A public storefront, and the booking flow that starts from it: pick a
	 * service, pick a free slot (already resolved across every qualified
	 * provider — discovery.js's `getPublicAvailability`), confirm. Booking
	 * itself needs a signed-in customer (`get_principal`); browsing does not.
	 *
	 * `recordReferral` fires once on mount — the marketplace click NOVA's own
	 * billing traces commission to (ADR-0008) — and the token it returns rides
	 * along on `createBooking` so this booking is attributed `marketplace`.
	 */
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { getStorefront, recordReferral } from '$lib/api/discovery.js';
	import { createBooking } from '$lib/api/booking.js';
	import { createPaymentIntent } from '$lib/api/payment.js';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { customerTenantsStore } from '$lib/stores/customerTenants.svelte.js';
	import { formatApiError, errorMessage } from '$lib/utils/errors.js';
	import { pickBilingual } from '$lib/utils/bilingual.js';
	import { formatDateTime } from '$lib/utils/datetime.js';
	import { formatMoney } from '$lib/utils/money.js';

	import Spinner from '$lib/components/ui/Spinner.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import ServiceCard from '$lib/components/catalog/ServiceCard.svelte';
	import SlotPicker from '$lib/components/booking/SlotPicker.svelte';
	import BookingStatusBadge from '$lib/components/booking/BookingStatusBadge.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import Section from '$lib/components/marketing/Section.svelte';

	let slug = $derived(/** @type {string} */ (page.params.slug));

	let loading = $state(true);
	let loadError = $state(/** @type {string|null} */ (null));
	let storefront = $state(/** @type {import('$lib/api/discovery.js').Storefront|null} */ (null));
	let referralToken = $state(/** @type {string|null} */ (null));

	/** @type {import('$lib/api/discovery.js').StorefrontService|null} */
	let selectedService = $state(null);
	/** @type {import('$lib/api/booking.js').AvailableSlot|import('$lib/api/discovery.js').PublicSlot|null} */
	let selectedSlot = $state(null);

	let booking = $state(/** @type {import('$lib/api/booking.js').Booking|null} */ (null));
	let bookingError = $state(/** @type {string|null} */ (null));
	let confirming = $state(false);
	let payLoading = $state(false);

	const now = new Date();
	const dateFrom = now.toISOString();
	const dateTo = new Date(now.getTime() + 14 * 24 * 60 * 60 * 1000).toISOString();

	$effect(() => {
		let cancelled = false;
		loading = true;
		loadError = null;
		getStorefront(slug)
			.then((result) => {
				if (cancelled) return;
				storefront = result;
			})
			.catch((err) => {
				if (!cancelled) loadError = errorMessage(err);
			})
			.finally(() => {
				if (!cancelled) loading = false;
			});
		recordReferral(slug)
			.then((referral) => {
				if (!cancelled) referralToken = referral.referral_token;
			})
			.catch(() => {
				// Non-critical: booking still works, it just won't be
				// attributed to the marketplace referral.
			});
		return () => {
			cancelled = true;
		};
	});

	/** @param {import('$lib/api/catalog.js').Service|import('$lib/api/discovery.js').StorefrontService} service */
	function selectService(service) {
		selectedService = service;
		selectedSlot = null;
		booking = null;
		bookingError = null;
	}

	/** @param {import('$lib/api/booking.js').AvailableSlot|import('$lib/api/discovery.js').PublicSlot} slot */
	function selectSlot(slot) {
		selectedSlot = slot;
	}

	async function confirmBooking() {
		if (!storefront || !selectedService || !selectedSlot) return;
		bookingError = null;
		confirming = true;
		try {
			booking = await createBooking(storefront.tenant_id, {
				locationId: selectedSlot.location_id,
				serviceId: selectedService.id,
				providerId: selectedSlot.provider_id,
				startsAt: selectedSlot.starts_at,
				slotId: selectedSlot.slot_id,
				referralToken
			});
			customerTenantsStore.add(storefront.tenant_id, pickBilingual(storefront, 'name', 'en'));
			toastStore.success('Booking confirmed.');
		} catch (err) {
			bookingError = formatApiError(err);
		} finally {
			confirming = false;
		}
	}

	async function payNow() {
		if (!storefront || !booking) return;
		payLoading = true;
		try {
			const intent = await createPaymentIntent(storefront.tenant_id, {
				bookingId: booking.id,
				returnUrl: page.url.origin + resolve('/bookings')
			});
			if (intent.redirect_url) {
				window.location.href = intent.redirect_url;
			} else {
				toastStore.info('Payment is not configured for this business yet.');
			}
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			payLoading = false;
		}
	}
</script>

<svelte:head
	><title>{storefront ? pickBilingual(storefront, 'name', 'en') : 'Storefront'} — NOVA</title
	></svelte:head
>

{#if loading}
	<Container size="lg" class="py-16 sm:py-24">
		<div class="flex justify-center"><Spinner /></div>
	</Container>
{:else if loadError}
	<Container size="lg" class="py-10 sm:py-14">
		<Alert tone="error">{loadError}</Alert>
	</Container>
{:else if storefront}
	<Section tone="sunken" padding="tight">
		<Container size="lg">
			<h1 class="text-display-md font-semibold tracking-tight text-slate-900 dark:text-slate-100">
				{pickBilingual(storefront, 'name', 'en')}
			</h1>
			{#if pickBilingual(storefront, 'description', 'en')}
				<p class="mt-2 text-slate-600 dark:text-slate-400">
					{pickBilingual(storefront, 'description', 'en')}
				</p>
			{/if}
			{#if storefront.locations.length > 0}
				<p class="mt-2 text-sm text-slate-500 dark:text-slate-400">
					{storefront.locations.map((l) => pickBilingual(l, 'name', 'en')).join(' · ')}
				</p>
			{/if}
		</Container>
	</Section>

	<Container size="lg" class="py-10 sm:py-14">
		<div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
			<div>
				<h2 class="mb-3 font-medium text-slate-900 dark:text-slate-100">Services</h2>
				{#if storefront.services.length === 0}
					<EmptyState title="No services listed yet" />
				{:else}
					<div class="flex flex-col gap-2">
						{#each storefront.services as service (service.id)}
							<ServiceCard
								{service}
								selected={selectedService?.id === service.id}
								onselect={selectService}
							/>
						{/each}
					</div>
				{/if}
			</div>

			<div>
				<h2 class="mb-3 font-medium text-slate-900 dark:text-slate-100">Pick a time</h2>
				{#if !selectedService}
					<EmptyState title="Choose a service first" />
				{:else if booking}
					<Card padding="md">
						<div class="flex items-start justify-between gap-3">
							<div>
								<p class="font-medium text-slate-900 dark:text-slate-100">
									{formatDateTime(booking.starts_at, 'en')}
								</p>
								<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">
									{formatMoney(booking.price, booking.currency, 'en')}
								</p>
							</div>
							<BookingStatusBadge status={booking.status} />
						</div>
						{#if booking.status === 'pending_payment'}
							<Button class="mt-4" fullWidth loading={payLoading} onclick={payNow}
								>Pay deposit</Button
							>
						{/if}
						<Button class="mt-2" fullWidth variant="outline" href={resolve('/bookings')}>
							View my bookings
						</Button>
					</Card>
				{:else}
					<SlotPicker
						source="public"
						{slug}
						serviceId={selectedService.id}
						{dateFrom}
						{dateTo}
						selectedSlotId={selectedSlot?.slot_id ?? null}
						onselect={selectSlot}
					/>

					{#if selectedSlot}
						<Card padding="md" class="mt-4">
							{#if bookingError}
								<Alert tone="error" class="mb-3">{bookingError}</Alert>
							{/if}
							{#if !authStore.isAuthenticated}
								<Alert tone="info">
									Sign in to complete this booking.
									<div class="mt-2 flex gap-2">
										<Button size="sm" href={resolve('/login')}>Sign in</Button>
										<Button size="sm" variant="outline" href={resolve('/register')}
											>Create account</Button
										>
									</div>
								</Alert>
							{:else}
								<p class="text-sm text-slate-600 dark:text-slate-300">
									{formatDateTime(selectedSlot.starts_at, 'en')} · {formatMoney(
										selectedService.price,
										selectedService.currency,
										'en'
									)}
								</p>
								<Button class="mt-3" fullWidth loading={confirming} onclick={confirmBooking}>
									Confirm booking
								</Button>
							{/if}
						</Card>
					{/if}
				{/if}
			</div>
		</div>
	</Container>
{/if}
