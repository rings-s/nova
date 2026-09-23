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
	import Card from '$lib/components/ui/Card.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import ServiceCard from '$lib/components/catalog/ServiceCard.svelte';
	import SlotPicker from '$lib/components/booking/SlotPicker.svelte';
	import BookingStatusBadge from '$lib/components/booking/BookingStatusBadge.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';
	import RatingStars from '$lib/components/review/RatingStars.svelte';
	import PhotoGallery from '$lib/components/discover/PhotoGallery.svelte';

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
	<title>{storefront ? pickBilingual(storefront, 'name', 'en') : 'Storefront'} — NOVA</title>
</svelte:head>

{#snippet step(/** @type {number} */ n, /** @type {string} */ label, /** @type {boolean} */ done)}
	<div class="mb-4 flex items-center gap-3">
		<span
			class={`flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${done ? 'bg-brand-600 text-white' : 'border border-line-strong text-fg-muted'}`}
		>
			{#if done}<Icon name="check" class="size-3.5" />{:else}{n}{/if}
		</span>
		<h2 class="text-base font-semibold tracking-tight text-fg">{label}</h2>
	</div>
{/snippet}

{#if loading}
	<Container size="lg" class="py-24">
		<div class="flex justify-center"><Spinner size="lg" /></div>
	</Container>
{:else if loadError}
	<Container size="lg" class="py-14">
		<Alert tone="error">{loadError}</Alert>
	</Container>
{:else if storefront}
	<!-- Salon header -->
	<section class="relative overflow-hidden border-b border-line bg-surface">
		<GradientBlob variant="hero" />
		<Container size="lg" class="relative z-10 py-10 sm:py-14">
			<a
				href={resolve('/discover')}
				class="mb-6 inline-flex items-center gap-1 text-sm font-medium text-fg-muted transition-colors hover:text-fg"
			>
				<Icon name="chevron-left" class="size-4 rtl:rotate-180" />
				All salons
			</a>
			{#if storefront.photos?.length}
				<div class="mb-8">
					<PhotoGallery photos={storefront.photos} name={pickBilingual(storefront, 'name', 'en')} />
				</div>
			{/if}
			<div class="flex flex-wrap items-end justify-between gap-8">
				<div class="max-w-2xl min-w-0">
					<h1 class="text-display-lg font-semibold tracking-tight text-fg">
						{pickBilingual(storefront, 'name', 'en')}
					</h1>
					{#if storefront.name_ar}
						<p class="mt-1 w-fit text-base text-fg-muted" dir="rtl" lang="ar">
							{storefront.name_ar}
						</p>
					{/if}
					<div class="mt-4">
						<RatingStars
							average={storefront.rating_average}
							count={storefront.rating_count}
							size="lg"
						/>
					</div>
					{#if pickBilingual(storefront, 'description', 'en')}
						<p class="mt-4 text-body-lg text-fg-secondary">
							{pickBilingual(storefront, 'description', 'en')}
						</p>
					{/if}
					{#if storefront.locations.length > 0}
						<div class="mt-5 flex flex-wrap gap-2">
							{#each storefront.locations as location (location.id)}
								<span
									class="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-fg-secondary"
								>
									<Icon name="map-pin" class="size-3.5 text-accent" />
									{pickBilingual(location, 'name', 'en')}
								</span>
							{/each}
						</div>
					{/if}
				</div>

				<ul class="grid gap-2.5 text-sm text-fg-secondary">
					{#each ['Instant WhatsApp confirmation', 'No double bookings — your slot is held', 'Apple Pay & Mada deposits'] as item (item)}
						<li class="flex items-center gap-2.5">
							<span
								class="flex size-5 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400"
							>
								<Icon name="check" class="size-3" />
							</span>
							{item}
						</li>
					{/each}
				</ul>
			</div>
		</Container>
	</section>

	<Container size="lg" class="py-10 sm:py-14">
		<div class="grid grid-cols-1 items-start gap-10 lg:grid-cols-12">
			<!-- 1. Services -->
			<section class="lg:col-span-7">
				<div class="flex items-center justify-between">
					{@render step(1, 'Choose a service', Boolean(selectedService))}
					<span class="mb-4 text-xs text-fg-muted">{storefront.services.length} available</span>
				</div>
				{#if storefront.services.length === 0}
					<EmptyState title="No services listed yet" />
				{:else}
					<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
						{#each storefront.services as service (service.id)}
							<ServiceCard
								{service}
								selected={selectedService?.id === service.id}
								onselect={selectService}
							/>
						{/each}
					</div>
				{/if}
			</section>

			<!-- 2–3. Time and confirmation, kept in view while the menu scrolls -->
			<section class="lg:sticky lg:top-24 lg:col-span-5">
				{#if booking}
					<Card padding="none" class="overflow-hidden">
						<div class="border-b border-line bg-emerald-50/70 px-6 py-5 dark:bg-emerald-500/10">
							<div class="flex items-center gap-3">
								<span
									class="flex size-10 items-center justify-center rounded-full bg-emerald-500 text-white"
								>
									<Icon name="check" class="size-5" />
								</span>
								<div>
									<p class="font-semibold text-fg">You're booked</p>
									<p class="text-sm text-fg-muted">{formatDateTime(booking.starts_at, 'en')}</p>
								</div>
							</div>
						</div>
						<div class="space-y-4 p-6">
							<div class="flex items-center justify-between text-sm">
								<span class="text-fg-muted">Status</span>
								<BookingStatusBadge status={booking.status} />
							</div>
							<div class="flex items-center justify-between text-sm">
								<span class="text-fg-muted">Total</span>
								<span class="font-semibold text-fg tabular-nums">
									{formatMoney(booking.price, booking.currency, 'en')}
								</span>
							</div>
							<p class="rounded-control bg-surface-sunken p-3 text-xs text-fg-secondary">
								A confirmation with your time and the salon's location is on its way to WhatsApp. If
								a deposit is due, pay it below to secure your slot.
							</p>
							{#if booking.status === 'pending_payment'}
								<Button fullWidth loading={payLoading} onclick={payNow}>Pay deposit</Button>
							{/if}
							<Button fullWidth variant="outline" href={resolve('/bookings')}>
								View my bookings
							</Button>
						</div>
					</Card>
				{:else}
					{@render step(2, 'Pick a time', Boolean(selectedSlot))}
					{#if !selectedService}
						<EmptyState
							title="Choose a service first"
							description="Available times appear here as soon as you pick a treatment."
						>
							{#snippet icon()}<Icon name="clock" class="size-6" />{/snippet}
						</EmptyState>
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
							<div class="mt-8">
								{@render step(3, 'Confirm', false)}
								<Card padding="none">
									<div class="space-y-3 p-5">
										{#if bookingError}
											<Alert tone="error">{bookingError}</Alert>
										{/if}
										<div class="flex items-start justify-between gap-4">
											<div class="min-w-0">
												<p class="truncate font-semibold text-fg">
													{pickBilingual(selectedService, 'name', 'en')}
												</p>
												<p class="text-sm text-fg-muted">
													{formatDateTime(selectedSlot.starts_at, 'en')}
												</p>
											</div>
											<span class="text-base font-semibold text-fg tabular-nums">
												{formatMoney(selectedService.price, selectedService.currency, 'en')}
											</span>
										</div>
									</div>
									<div class="rounded-b-card border-t border-line bg-surface-sunken p-5">
										{#if !authStore.isAuthenticated}
											<p class="mb-3 text-sm text-fg-secondary">
												Sign in to book — we'll send your confirmation on WhatsApp.
											</p>
											<div class="grid grid-cols-2 gap-2">
												<Button variant="outline" href={resolve('/register')}>Create account</Button
												>
												<Button href={resolve('/login')}>Sign in</Button>
											</div>
										{:else}
											<Button fullWidth size="lg" loading={confirming} onclick={confirmBooking}>
												Confirm booking
											</Button>
										{/if}
									</div>
								</Card>
							</div>
						{/if}
					{/if}
				{/if}
			</section>
		</div>
	</Container>
{/if}
