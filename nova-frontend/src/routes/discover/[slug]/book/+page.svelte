<script>
	import { t, intlLocale } from '$lib/i18n/index.svelte.js';
	/**
	 * Step 2 of the storefront booking flow, on a page of its own: the whole
	 * public availability window (`discovery_max_availability_days`, 14) as a
	 * full calendar. A day opens `TimeSlotModal` with its times; the chosen
	 * time lands in the summary, which confirms the booking.
	 *
	 * `?service=<id>` names the treatment, so the page survives a reload and
	 * the sign-in round trip (`/login?next=`). The storefront recorded the
	 * marketplace referral; its token comes across through
	 * `recallReferral` rather than a second click being recorded here.
	 */
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { getStorefront } from '$lib/api/discovery.js';
	import { createBooking } from '$lib/api/booking.js';
	import { createPaymentIntent } from '$lib/api/payment.js';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { customerTenantsStore } from '$lib/stores/customerTenants.svelte.js';
	import { formatApiError, errorMessage } from '$lib/utils/errors.js';
	import { pickBilingual } from '$lib/utils/bilingual.js';
	import { dateKey, formatDateTime, formatTime } from '$lib/utils/datetime.js';
	import { formatMoney } from '$lib/utils/money.js';
	import { minutesLabel } from '$lib/i18n/labels.js';
	import { recallReferral } from '$lib/utils/referral.js';
	import Container from '$lib/components/marketing/Container.svelte';
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import BookingStatusBadge from '$lib/components/booking/BookingStatusBadge.svelte';
	import AvailabilityCalendar from '$lib/components/booking/AvailabilityCalendar.svelte';
	import TimeSlotModal from '$lib/components/booking/TimeSlotModal.svelte';
	import {
		fetchSlots,
		groupSlotsByDay,
		dayKeyToDate
	} from '$lib/components/booking/availability.js';

	let slug = $derived(/** @type {string} */ (page.params.slug));
	let serviceId = $derived(page.url.searchParams.get('service') ?? '');

	let loading = $state(true);
	let loadError = $state(/** @type {string|null} */ (null));
	let storefront = $state(/** @type {import('$lib/api/discovery.js').Storefront|null} */ (null));
	let service = $derived(storefront?.services.find((s) => s.id === serviceId) ?? null);

	// Read only when booking, in the browser (sessionStorage).
	let referralToken = $derived(recallReferral(slug));

	$effect(() => {
		let cancelled = false;
		loading = true;
		loadError = null;
		getStorefront(slug)
			.then((result) => {
				if (!cancelled) storefront = result;
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

	// --- Availability --------------------------------------------------------------

	const now = new Date();
	const dateFrom = now.toISOString();
	const dateTo = new Date(now.getTime() + 14 * 24 * 60 * 60 * 1000).toISOString();
	const fromKey = dateKey(dateFrom);
	const toKey = dateKey(dateTo);

	let slotsLoading = $state(true);
	let slotsError = $state(/** @type {string|null} */ (null));
	let slots = $state(/** @type {import('$lib/components/booking/availability.js').Slot[]} */ ([]));
	let slotsByDay = $derived(groupSlotsByDay(slots));
	let earliest = $derived(
		slots.length ? [...slots].sort((a, b) => a.starts_at.localeCompare(b.starts_at))[0] : null
	);

	$effect(() => {
		if (!service) return;
		let cancelled = false;
		slotsLoading = true;
		slotsError = null;
		fetchSlots({ source: 'public', slug, serviceId: service.id, dateFrom, dateTo })
			.then((items) => {
				if (!cancelled) slots = items;
			})
			.catch((err) => {
				if (!cancelled) slotsError = errorMessage(err);
			})
			.finally(() => {
				if (!cancelled) slotsLoading = false;
			});
		return () => {
			cancelled = true;
		};
	});

	// --- Picking a time --------------------------------------------------------------

	/** The day whose times the modal shows; `null` while it is closed. */
	let modalDayKey = $state(/** @type {string|null} */ (null));
	let selectedSlot = $state(
		/** @type {import('$lib/components/booking/availability.js').Slot|null} */ (null)
	);
	let selectedDayKey = $derived(
		modalDayKey ?? (selectedSlot ? dateKey(selectedSlot.starts_at) : null)
	);

	/** @param {import('$lib/components/booking/availability.js').Slot} slot */
	function chooseSlot(slot) {
		selectedSlot = slot;
		bookingError = null;
		modalDayKey = null;
	}

	/** @param {string} key */
	function formatDayLong(key) {
		return new Intl.DateTimeFormat(intlLocale(), {
			weekday: 'long',
			day: 'numeric',
			month: 'long',
			timeZone: 'UTC'
		}).format(dayKeyToDate(key));
	}

	// --- Booking ---------------------------------------------------------------------

	let booking = $state(/** @type {import('$lib/api/booking.js').Booking|null} */ (null));
	let bookingError = $state(/** @type {string|null} */ (null));
	let confirming = $state(false);
	let payLoading = $state(false);

	let signInHref = $derived(
		`${resolve('/login')}?next=${encodeURIComponent(page.url.pathname + page.url.search)}`
	);

	async function confirmBooking() {
		if (!storefront || !service || !selectedSlot) return;
		bookingError = null;
		confirming = true;
		try {
			booking = await createBooking(storefront.tenant_id, {
				locationId: selectedSlot.location_id,
				serviceId: service.id,
				providerId: selectedSlot.provider_id,
				startsAt: selectedSlot.starts_at,
				slotId: selectedSlot.slot_id,
				referralToken
			});
			customerTenantsStore.add(storefront.tenant_id, pickBilingual(storefront, 'name'));
			// A self-service booking starts as a draft; staff or a payment confirms it.
			toastStore.success(
				booking.status === 'confirmed'
					? t('Booking confirmed.')
					: t('Booking received. The salon will confirm it.')
			);
			window.scrollTo({ top: 0, behavior: 'smooth' });
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
				// Moyasar sends the payer back here, with `payment=<id>` added.
				returnUrl: `${page.url.origin}${resolve('/bookings')}?tenant=${encodeURIComponent(storefront.tenant_id)}`
			});
			if (intent.redirect_url) {
				window.location.href = intent.redirect_url;
			} else {
				toastStore.info(t('Payment is not configured for this business yet.'));
			}
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			payLoading = false;
		}
	}

	let storefrontHref = $derived(resolve('/discover/[slug]', { slug }));
</script>

<svelte:head>
	<title>{t('Choose a date')} — {storefront ? pickBilingual(storefront, 'name') : 'NOVA'}</title>
</svelte:head>

{#snippet stepper(/** @type {number} */ current)}
	<ol class="flex items-center gap-2 text-xs font-medium sm:gap-3" aria-label={t('Booking steps')}>
		{#each [t('Service'), t('Date & time'), t('Confirm')] as label, i (i)}
			{@const n = i + 1}
			{@const done = n < current}
			{@const active = n === current}
			{#if i > 0}
				<li
					aria-hidden="true"
					class={['h-px w-5 sm:w-8', done || active ? 'bg-brand-400' : 'bg-line-strong'].join(' ')}
				></li>
			{/if}
			<li class="flex items-center gap-2" aria-current={active ? 'step' : undefined}>
				<span
					class={[
						'flex size-6 items-center justify-center rounded-full text-[11px] font-semibold',
						done
							? 'bg-brand-600 text-white'
							: active
								? 'bg-brand-600 text-white ring-4 ring-brand-500/20'
								: 'border border-line-strong text-fg-muted'
					].join(' ')}
				>
					{#if done}<Icon name="check" class="size-3" />{:else}{n}{/if}
				</span>
				<span class={['hidden sm:inline', active ? 'text-fg' : 'text-fg-muted'].join(' ')}
					>{label}</span
				>
			</li>
		{/each}
	</ol>
{/snippet}

{#snippet summaryRows()}
	{#if service}
		<div class="flex items-start justify-between gap-4">
			<div class="min-w-0">
				<p class="truncate font-semibold text-fg">{pickBilingual(service, 'name')}</p>
				<p class="mt-0.5 flex items-center gap-1.5 text-sm text-fg-muted">
					<Icon name="clock" class="size-3.5" />
					{minutesLabel(service.duration_minutes)}
				</p>
			</div>
			<span class="text-base font-semibold text-fg tabular-nums">
				{formatMoney(service.price, service.currency)}
			</span>
		</div>
	{/if}
{/snippet}

{#if loading}
	<Container size="lg" class="py-10 sm:py-14">
		<Skeleton class="mb-4 h-4 w-32" />
		<Skeleton class="mb-10 h-9 w-72" />
		<div class="grid gap-8 lg:grid-cols-12">
			<Skeleton class="h-[28rem] w-full rounded-card lg:col-span-8" />
			<Skeleton class="h-64 w-full rounded-card lg:col-span-4" />
		</div>
	</Container>
{:else if loadError}
	<Container size="lg" class="py-14">
		<Alert tone="error">{loadError}</Alert>
	</Container>
{:else if storefront && !service}
	<Container size="md" class="py-20">
		<EmptyState
			title={t('Choose a service first')}
			description={t('Pick a treatment on the salon page, then choose when.')}
		>
			{#snippet icon()}<Icon name="calendar" class="size-6" />{/snippet}
		</EmptyState>
		<div class="mt-6 flex justify-center">
			<Button href={storefrontHref}>{t('See services')}</Button>
		</div>
	</Container>
{:else if storefront && service}
	<!-- Header -->
	<section class="relative overflow-hidden border-b border-line bg-surface">
		<GradientBlob variant="hero" />
		<Container size="lg" class="relative z-10 py-8 sm:py-10">
			<div class="flex flex-wrap items-center justify-between gap-4">
				<a
					href={resolve('/discover/[slug]', { slug })}
					class="inline-flex items-center gap-1 text-sm font-medium text-fg-muted transition-colors hover:text-fg"
				>
					<Icon name="chevron-left" class="size-4 rtl:rotate-180" />
					{pickBilingual(storefront, 'name')}
				</a>
				{@render stepper(booking ? 4 : selectedSlot ? 3 : 2)}
			</div>
			<h1 class="mt-6 text-display-md font-semibold tracking-tight text-fg">
				{booking ? t("You're booked") : selectedSlot ? t('Review and confirm') : t('Choose a date')}
			</h1>
			<p class="mt-2 text-body-lg text-fg-secondary">
				{pickBilingual(service, 'name')} · {minutesLabel(service.duration_minutes)} · {formatMoney(
					service.price,
					service.currency
				)}
			</p>
		</Container>
	</section>

	<Container size="lg" class="py-10 pb-32 sm:py-12 lg:pb-12">
		{#if booking}
			<!-- Done -->
			<div class="mx-auto max-w-lg">
				<Card padding="none" class="overflow-hidden">
					<div class="border-b border-line bg-emerald-50/70 px-6 py-5 dark:bg-emerald-500/10">
						<div class="flex items-center gap-3">
							<span
								class="flex size-10 items-center justify-center rounded-full bg-emerald-500 text-white"
							>
								<Icon name="check" class="size-5" />
							</span>
							<div>
								<p class="font-semibold text-fg">{t("You're booked")}</p>
								<p class="text-sm text-fg-muted">{formatDateTime(booking.starts_at)}</p>
							</div>
						</div>
					</div>
					<div class="space-y-4 p-6">
						{@render summaryRows()}
						<div class="flex items-center justify-between border-t border-line pt-4 text-sm">
							<span class="text-fg-muted">{t('Status')}</span>
							<BookingStatusBadge status={booking.status} />
						</div>
						<div class="flex items-center justify-between text-sm">
							<span class="text-fg-muted">{t('Total')}</span>
							<span class="font-semibold text-fg tabular-nums">
								{formatMoney(booking.price, booking.currency)}
							</span>
						</div>
						<p class="rounded-control bg-surface-sunken p-3 text-xs text-fg-secondary">
							{t(
								"A confirmation with your time and the salon's location is on its way to WhatsApp. If a deposit is due, pay it below to secure your slot."
							)}
						</p>
						{#if booking.status === 'pending_payment'}
							<Button fullWidth loading={payLoading} onclick={payNow}>{t('Pay deposit')}</Button>
						{/if}
						<Button fullWidth variant="outline" href={resolve('/bookings')}>
							{t('View my bookings')}
						</Button>
					</div>
				</Card>
			</div>
		{:else}
			<div class="grid grid-cols-1 items-start gap-8 lg:grid-cols-12">
				<!-- Calendar -->
				<Card padding="lg" class="lg:col-span-8">
					<div class="mb-6 flex flex-wrap items-center justify-between gap-3">
						<div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-fg-muted">
							<span class="inline-flex items-center gap-1.5">
								<span
									class="rounded-full bg-accent-soft px-1.5 text-[10px] leading-4 font-semibold text-accent"
									>8</span
								>{t('Free times that day')}
							</span>
							<span class="inline-flex items-center gap-1.5">
								<span class="size-2.5 rounded-[3px] ring-1 ring-brand-400 ring-inset"></span>{t(
									'Today'
								)}
							</span>
							<span class="inline-flex items-center gap-1.5">
								<span class="text-fg-subtle/60 tabular-nums">12</span>{t('Unavailable')}
							</span>
						</div>
						{#if earliest}
							<Button
								variant="outline"
								size="sm"
								onclick={() => (modalDayKey = dateKey(earliest.starts_at))}
							>
								<Icon name="zap" class="size-3.5 text-accent" />
								{t('Earliest: {time}', {
									time: `${formatDayLong(dateKey(earliest.starts_at))}, ${formatTime(earliest.starts_at)}`
								})}
							</Button>
						{/if}
					</div>

					{#if slotsLoading}
						<div class="grid grid-cols-7 gap-1.5">
							{#each Array.from({ length: 35 }, (_, i) => i) as i (i)}
								<Skeleton class="aspect-square w-full rounded-control sm:aspect-[5/4]" />
							{/each}
						</div>
					{:else if slotsError}
						<Alert tone="error">{slotsError}</Alert>
					{:else if slots.length === 0}
						<EmptyState
							title={t('No free slots')}
							description={t('Nothing is free in the next two weeks. Try another service.')}
						>
							{#snippet icon()}<Icon name="clock" class="size-6" />{/snippet}
						</EmptyState>
					{:else}
						<AvailabilityCalendar
							variant="full"
							{slotsByDay}
							{fromKey}
							{toKey}
							{selectedDayKey}
							onselectday={(key) => (modalDayKey = key)}
						/>
						<p class="mt-6 flex items-center gap-2 text-xs text-fg-muted">
							<Icon name="info" class="size-3.5" />
							{t('Pick a day to see its times. Times are in the salon’s local time.')}
						</p>
					{/if}
				</Card>

				<!-- Summary -->
				<aside id="booking-summary" class="lg:sticky lg:top-24 lg:col-span-4">
					<Card padding="none">
						<div class="space-y-4 p-5">
							<p class="text-[11px] font-semibold tracking-wider text-fg-subtle uppercase">
								{t('Your booking')}
							</p>
							{@render summaryRows()}
							<div class="rounded-control border border-dashed border-line-strong p-4">
								{#if selectedSlot}
									<div class="flex items-start justify-between gap-3">
										<div class="min-w-0 space-y-1">
											<p class="font-semibold text-fg">
												{formatDayLong(dateKey(selectedSlot.starts_at))}
											</p>
											<p class="flex items-center gap-1.5 text-sm text-fg-muted tabular-nums">
												<Icon name="clock" class="size-3.5 shrink-0" />
												{formatTime(selectedSlot.starts_at)} – {formatTime(selectedSlot.ends_at)}
											</p>
											{#if 'provider_name_en' in selectedSlot}
												<p class="flex items-center gap-1.5 text-sm text-fg-muted">
													<Icon name="user" class="size-3.5 shrink-0" />
													<span class="truncate"
														>{pickBilingual(selectedSlot, 'provider_name')}</span
													>
												</p>
											{/if}
										</div>
										<Button
											variant="ghost"
											size="sm"
											class="-me-2 shrink-0"
											onclick={() =>
												selectedSlot && (modalDayKey = dateKey(selectedSlot.starts_at))}
										>
											{t('Change')}
										</Button>
									</div>
								{:else}
									<p class="flex items-center gap-2 text-sm text-fg-muted">
										<Icon name="calendar" class="size-4" />
										{t('No time chosen yet')}
									</p>
								{/if}
							</div>
							{#if bookingError}
								<Alert tone="error">{bookingError}</Alert>
							{/if}
						</div>
						<div class="rounded-b-card border-t border-line bg-surface-sunken p-5">
							{#if !authStore.isAuthenticated}
								<p class="mb-3 text-sm text-fg-secondary">
									{t("Sign in to book — we'll send your confirmation on WhatsApp.")}
								</p>
								<div class="grid grid-cols-2 gap-2">
									<Button variant="outline" href={`${resolve('/register')}?as=customer`}>
										{t('Create account')}
									</Button>
									<Button href={signInHref}>{t('Sign in')}</Button>
								</div>
							{:else}
								<Button
									fullWidth
									size="lg"
									disabled={!selectedSlot}
									loading={confirming}
									onclick={confirmBooking}
								>
									{t('Confirm booking')}
								</Button>
							{/if}
						</div>
					</Card>
				</aside>
			</div>

			<!-- Phone: the summary sits below the calendar, so keep the chosen time and its action in reach. -->
			{#if selectedSlot}
				<div
					class="fixed inset-x-0 bottom-0 z-40 animate-fade-in border-t border-line bg-surface/95 px-4 py-3 shadow-overlay backdrop-blur lg:hidden"
				>
					<div class="mx-auto flex max-w-lg items-center justify-between gap-3">
						<div class="min-w-0">
							<p class="truncate text-sm font-semibold text-fg">
								{formatDayLong(dateKey(selectedSlot.starts_at))}
							</p>
							<p class="text-xs text-fg-muted tabular-nums">{formatTime(selectedSlot.starts_at)}</p>
						</div>
						{#if authStore.isAuthenticated}
							<Button loading={confirming} onclick={confirmBooking}>{t('Confirm booking')}</Button>
						{:else}
							<Button href={signInHref}>{t('Sign in to book')}</Button>
						{/if}
					</div>
				</div>
			{/if}
		{/if}
	</Container>

	<TimeSlotModal
		open={modalDayKey !== null}
		dayKey={modalDayKey}
		{slotsByDay}
		selectedSlotId={selectedSlot?.slot_id ?? null}
		subtitle={pickBilingual(service, 'name')}
		onselect={chooseSlot}
		onchangeday={(key) => (modalDayKey = key)}
		onclose={() => (modalDayKey = null)}
	/>
{/if}
