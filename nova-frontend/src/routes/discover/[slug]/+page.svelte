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
	import Button from '$lib/components/ui/Button.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import ServiceCard from '$lib/components/catalog/ServiceCard.svelte';
	import SlotPicker from '$lib/components/booking/SlotPicker.svelte';
	import BookingStatusBadge from '$lib/components/booking/BookingStatusBadge.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';

	let slug = $derived(/** @type {string} */ (page.params.slug));
	let loading = $state(true);
	let loadError = $state(/** @type {string|null} */ (null));
	let storefront = $state(/** @type {import('$lib/api/discovery.js').Storefront|null} */ (null));
	let referralToken = $state(/** @type {string|null} */ (null));

	/** @type {import('$lib/api/catalog.js').Service|import('$lib/api/discovery.js').StorefrontService|null} */
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
				// Non-critical
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

<svelte:head>
	<title
		>{storefront ? pickBilingual(storefront, 'name', 'en') : 'Storefront'} — Verified GCC Salon | NOVA</title
	>
</svelte:head>

{#if loading}
	<Container size="lg" class="py-24">
		<div class="flex flex-col items-center justify-center">
			<Spinner size="lg" />
			<p class="mt-4 font-mono text-xs text-slate-500">
				Loading salon storefront &amp; verified schedule...
			</p>
		</div>
	</Container>
{:else if loadError}
	<Container size="lg" class="py-14">
		<Alert tone="error">{loadError}</Alert>
	</Container>
{:else if storefront}
	<!-- Salon Hero Header -->
	<section
		class="relative overflow-hidden border-b border-slate-200 bg-white py-10 sm:py-14 dark:border-slate-800 dark:bg-slate-900"
	>
		<GradientBlob variant="hero" />
		<Container size="lg" class="relative z-10">
			<!-- Telemetry Status Line -->
			<div class="flex flex-wrap items-center justify-between gap-3">
				<div
					class="inline-flex items-center gap-2 rounded-full border border-slate-200/80 bg-white/90 px-3.5 py-1 text-xs font-semibold text-slate-700 shadow-xs backdrop-blur dark:border-slate-800 dark:bg-slate-800 dark:text-slate-300"
				>
					<span class="size-2 animate-pulse rounded-full bg-emerald-500"></span>
					<span class="font-bold text-slate-900 dark:text-slate-100"
						>Live Concurrency Protection</span
					>
					<span class="text-slate-300 dark:text-slate-600">·</span>
					<span>Deterministic 10-min Holds</span>
				</div>
			</div>

			<div class="mt-6 flex flex-wrap items-start justify-between gap-6">
				<div>
					<div class="flex items-center gap-2.5">
						{#if storefront.locations.length > 0}
							<span class="text-xs font-medium text-slate-500">
								{storefront.locations.length}
								{storefront.locations.length === 1 ? 'Location' : 'Locations'}
							</span>
						{/if}
					</div>

					<h1
						class="mt-3 text-display-md font-extrabold tracking-tight text-slate-900 sm:text-display-lg dark:text-slate-100"
					>
						{pickBilingual(storefront, 'name', 'en')}
					</h1>

					{#if storefront.name_ar}
						<p class="mt-1 font-sans text-sm text-slate-500 dark:text-slate-400" dir="rtl">
							{storefront.name_ar}
						</p>
					{/if}

					{#if pickBilingual(storefront, 'description', 'en')}
						<p class="mt-3 max-w-2xl text-xs leading-relaxed text-slate-600 dark:text-slate-400">
							{pickBilingual(storefront, 'description', 'en')}
						</p>
					{/if}

					{#if storefront.locations.length > 0}
						<div class="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-500">
							<Icon name="map-pin" class="size-3.5 text-brand-600" />
							<span
								>{storefront.locations.map((l) => pickBilingual(l, 'name', 'en')).join(' · ')}</span
							>
						</div>
					{/if}
				</div>

				<div
					class="rounded-3xl border border-slate-200 bg-slate-50/80 p-5 backdrop-blur dark:border-slate-800 dark:bg-slate-800/60"
				>
					<span class="text-xs font-bold tracking-wider text-slate-500 uppercase"
						>Salon Guarantees</span
					>
					<ul class="mt-3 space-y-2 text-xs text-slate-700 dark:text-slate-300">
						<li class="flex items-center gap-2">
							<Icon name="check" class="size-3.5 text-emerald-600" />
							<span>Instant WhatsApp confirmation &amp; reminders</span>
						</li>
						<li class="flex items-center gap-2">
							<Icon name="check" class="size-3.5 text-emerald-600" />
							<span>Zero double bookings guaranteed</span>
						</li>
						<li class="flex items-center gap-2">
							<Icon name="check" class="size-3.5 text-emerald-600" />
							<span>Apple Pay &amp; Mada deposits via Moyasar</span>
						</li>
					</ul>
				</div>
			</div>
		</Container>
	</section>

	<!-- Booking Interface Grid -->
	<Container size="lg" class="py-10 sm:py-14">
		<div class="grid grid-cols-1 gap-8 lg:grid-cols-12">
			<!-- Service Menu List -->
			<div class="lg:col-span-6">
				<div class="mb-4 flex items-center justify-between">
					<h2 class="text-base font-bold text-slate-900 dark:text-slate-100">
						Signature Treatments &amp; Services
					</h2>
					<span class="text-xs font-medium text-slate-500">
						{storefront.services.length} available
					</span>
				</div>

				{#if storefront.services.length === 0}
					<EmptyState title="No services listed yet" />
				{:else}
					<div class="flex flex-col gap-3">
						{#each storefront.services as service (service.id)}
							<div class="cursor-pointer transition-all">
								<ServiceCard
									{service}
									selected={selectedService?.id === service.id}
									onselect={selectService}
								/>
							</div>
						{/each}
					</div>
				{/if}
			</div>

			<!-- Slot Picker & Checkout Desk -->
			<div class="lg:col-span-6">
				<div class="mb-4 flex items-center justify-between">
					<h2 class="text-base font-bold text-slate-900 dark:text-slate-100">
						Select Date &amp; Time
					</h2>
					{#if selectedService}
						<span class="text-xs font-semibold text-brand-600 dark:text-brand-400">
							{pickBilingual(selectedService, 'name', 'en')}
						</span>
					{/if}
				</div>

				{#if !selectedService}
					<div
						class="rounded-3xl border border-dashed border-slate-300 bg-white p-10 text-center shadow-xs dark:border-slate-800 dark:bg-slate-900"
					>
						<div
							class="mx-auto flex size-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-950/60 dark:text-brand-400"
						>
							<Icon name="sparkles" class="size-6" />
						</div>
						<h3 class="mt-4 text-base font-bold text-slate-900 dark:text-slate-100">
							Choose a service to view live slots
						</h3>
						<p class="mx-auto mt-1 max-w-xs text-xs text-slate-500 dark:text-slate-400">
							Click any treatment on the left to inspect real-time chair availability across our
							therapists.
						</p>
					</div>
				{:else if booking}
					<div
						class="rounded-3xl border border-emerald-300 bg-white p-6 shadow-md ring-2 ring-emerald-500/20 dark:border-emerald-800 dark:bg-slate-900"
					>
						<div
							class="flex items-start justify-between gap-3 border-b border-slate-100 pb-4 dark:border-slate-800"
						>
							<div>
								<span
									class="text-[11px] font-bold tracking-wider text-emerald-600 uppercase dark:text-emerald-400"
								>
									Appointment Confirmed
								</span>
								<p class="mt-1 text-base font-bold text-slate-900 dark:text-slate-100">
									{formatDateTime(booking.starts_at, 'en')}
								</p>
								<p class="mt-0.5 text-xs text-slate-500">
									Total: {formatMoney(booking.price, booking.currency, 'en')}
								</p>
							</div>
							<BookingStatusBadge status={booking.status} />
						</div>

						<div
							class="mt-4 rounded-2xl bg-slate-50 p-3.5 text-xs text-slate-600 dark:bg-slate-800/60 dark:text-slate-300"
						>
							<p>
								A confirmation with your appointment time and salon location was prepared. If you
								selected deposit, pay below to lock your chair.
							</p>
						</div>

						{#if booking.status === 'pending_payment'}
							<div class="mt-4">
								<Button fullWidth loading={payLoading} onclick={payNow}>
									Pay Deposit via Apple Pay / Mada
								</Button>
							</div>
						{/if}

						<div class="mt-3">
							<Button fullWidth variant="outline" href={resolve('/bookings')}>
								View in My Bookings
							</Button>
						</div>
					</div>
				{:else}
					<div
						class="rounded-3xl border border-slate-200 bg-white p-6 shadow-xs dark:border-slate-800 dark:bg-slate-900"
					>
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
							<div
								class="mt-6 rounded-2xl border border-brand-200 bg-brand-50/60 p-4 dark:border-brand-900/60 dark:bg-brand-950/40"
							>
								{#if bookingError}
									<Alert tone="error" class="mb-3">{bookingError}</Alert>
								{/if}

								<div class="flex items-center justify-between">
									<div>
										<span
											class="text-[11px] font-bold tracking-wider text-brand-700 uppercase dark:text-brand-300"
										>
											Selected Slot
										</span>
										<p class="text-xs font-bold text-slate-900 dark:text-slate-100">
											{formatDateTime(selectedSlot.starts_at, 'en')}
										</p>
									</div>
									<span
										class="font-mono text-base font-extrabold text-slate-900 dark:text-slate-100"
									>
										{formatMoney(selectedService.price, selectedService.currency, 'en')}
									</span>
								</div>

								{#if !authStore.isAuthenticated}
									<div
										class="mt-4 rounded-xl border border-brand-200 bg-white p-3 text-xs dark:border-slate-800 dark:bg-slate-900"
									>
										<p class="text-slate-700 dark:text-slate-300">
											Please sign in or create an account to secure this appointment with instant
											WhatsApp alerts.
										</p>
										<div class="mt-3 flex gap-2">
											<Button size="sm" href={resolve('/login')}>Sign in</Button>
											<Button size="sm" variant="outline" href={resolve('/register')}>
												Create account
											</Button>
										</div>
									</div>
								{:else}
									<div class="mt-4">
										<Button fullWidth loading={confirming} onclick={confirmBooking}>
											Lock Chair &amp; Confirm Booking
										</Button>
									</div>
								{/if}
							</div>
						{/if}
					</div>
				{/if}
			</div>
		</div>
	</Container>
{/if}
