<script>
	import { t, m, i18n } from '$lib/i18n/index.svelte.js';
	/**
	 * A public storefront: the salon, its photos and its menu. Picking a
	 * service leads to `/discover/[slug]/book?service=<id>`, the full-page
	 * calendar where the time is chosen (in a modal) and the booking made.
	 * Browsing needs no account; booking needs a signed-in customer.
	 *
	 * `recordReferral` fires once on mount — the marketplace click NOVA's own
	 * billing traces commission to (ADR-0008). Its token is kept for the
	 * booking page (`rememberReferral`), which sends it on `createBooking` so
	 * the booking is attributed `marketplace`.
	 */
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { getStorefront, recordReferral } from '$lib/api/discovery.js';
	import { errorMessage } from '$lib/utils/errors.js';
	import { pickBilingual } from '$lib/utils/bilingual.js';
	import { formatMoney } from '$lib/utils/money.js';
	import { rememberReferral } from '$lib/utils/referral.js';
	import { minutesLabel } from '$lib/i18n/labels.js';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import ServiceCard from '$lib/components/catalog/ServiceCard.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';
	import RatingStars from '$lib/components/review/RatingStars.svelte';
	import PhotoGallery from '$lib/components/discover/PhotoGallery.svelte';
	import AssistantLauncher from '$lib/components/ai/AssistantLauncher.svelte';

	let slug = $derived(/** @type {string} */ (page.params.slug));
	let loading = $state(true);
	let loadError = $state(/** @type {string|null} */ (null));
	let storefront = $state(/** @type {import('$lib/api/discovery.js').Storefront|null} */ (null));
	let referralToken = $state(/** @type {string|null} */ (null));

	/** @type {import('$lib/api/catalog.js').Service|import('$lib/api/discovery.js').StorefrontService|null} */
	let selectedService = $state(null);

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
				if (cancelled) return;
				referralToken = referral.referral_token;
				rememberReferral(slug, referral);
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
	}

	/** @param {string} serviceId */
	function bookHref(serviceId) {
		return `${resolve('/discover/[slug]/book', { slug })}?service=${encodeURIComponent(serviceId)}`;
	}
</script>

<svelte:head>
	<title>{storefront ? pickBilingual(storefront, 'name') : t('Storefront')} — NOVA</title>
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
				{t('All venues')}
			</a>
			{#if storefront.photos?.length}
				<div class="mb-8">
					<PhotoGallery photos={storefront.photos} name={pickBilingual(storefront, 'name')} />
				</div>
			{/if}
			<div class="flex flex-wrap items-end justify-between gap-8">
				<div class="max-w-2xl min-w-0">
					<h1 class="text-display-lg font-semibold tracking-tight text-fg">
						{pickBilingual(storefront, 'name')}
					</h1>
					{#if i18n.locale === 'en' && storefront.name_ar}
						<p class="mt-1 w-fit text-base text-fg-muted" dir="rtl" lang="ar">
							{storefront.name_ar}
						</p>
					{:else if i18n.locale === 'ar' && storefront.name_en}
						<p class="mt-1 w-fit text-base text-fg-muted" dir="ltr" lang="en">
							{storefront.name_en}
						</p>
					{/if}
					<div class="mt-4">
						<RatingStars
							average={storefront.rating_average}
							count={storefront.rating_count}
							size="lg"
						/>
					</div>
					{#if pickBilingual(storefront, 'description')}
						<p class="mt-4 text-body-lg text-fg-secondary">
							{pickBilingual(storefront, 'description')}
						</p>
					{/if}
					{#if storefront.locations.length > 0}
						<div class="mt-5 flex flex-wrap gap-2">
							{#each storefront.locations as location (location.id)}
								<span
									class="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-fg-secondary"
								>
									<Icon name="map-pin" class="size-3.5 text-accent" />
									{pickBilingual(location, 'name')}
								</span>
							{/each}
						</div>
					{/if}
				</div>

				<ul class="grid gap-2.5 text-sm text-fg-secondary">
					{#each [m('Instant WhatsApp confirmation'), m('No double bookings — your slot is held'), m('Apple Pay & Mada deposits')] as item (item)}
						<li class="flex items-center gap-2.5">
							<span
								class="flex size-5 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400"
							>
								<Icon name="check" class="size-3" />
							</span>
							{t(item)}
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
					{@render step(1, t('Choose a service'), Boolean(selectedService))}
					<span class="mb-4 text-xs text-fg-muted"
						>{t('{count} available', { count: storefront.services.length })}</span
					>
				</div>
				{#if storefront.services.length === 0}
					<EmptyState title={t('No services listed yet')} />
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

			<!-- 2. Hand-off to the calendar, kept in view while the menu scrolls -->
			<section class="lg:sticky lg:top-24 lg:col-span-5">
				{@render step(2, t('Pick a date & time'), false)}
				{#if !selectedService}
					<EmptyState
						title={t('Choose a service first')}
						description={t('Then pick a day on the calendar and a time that suits you.')}
					>
						{#snippet icon()}<Icon name="calendar" class="size-6" />{/snippet}
					</EmptyState>
				{:else}
					<Card padding="none" class="overflow-hidden">
						<div class="space-y-1 p-5">
							<div class="flex items-start justify-between gap-4">
								<p class="min-w-0 truncate font-semibold text-fg">
									{pickBilingual(selectedService, 'name')}
								</p>
								<span class="text-base font-semibold text-fg tabular-nums">
									{formatMoney(selectedService.price, selectedService.currency)}
								</span>
							</div>
							<p class="flex items-center gap-1.5 text-sm text-fg-muted">
								<Icon name="clock" class="size-3.5" />
								{minutesLabel(selectedService.duration_minutes)}
							</p>
						</div>
						<div class="border-t border-line bg-surface-sunken p-5">
							<Button fullWidth size="lg" href={bookHref(selectedService.id)}>
								<Icon name="calendar" class="size-4" />
								{t('Choose date & time')}
								<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
							</Button>
							<p class="mt-3 text-center text-xs text-fg-muted">
								{t('See the next two weeks at a glance.')}
							</p>
						</div>
					</Card>
				{/if}
			</section>
		</div>
	</Container>
	<AssistantLauncher
		tenantId={storefront.tenant_id}
		agent="receptionist_agent"
		businessId={storefront.business_id}
		{referralToken}
		title={t('Booking assistant')}
		subtitle={pickBilingual(storefront, 'name')}
		intro={t(
			'Tell me what you would like and when. I find a free time, hold it, and book it once you say yes.'
		)}
		starters={[
			t('Which services do you offer?'),
			t('What times are free tomorrow?'),
			t('Book me the earliest slot this week')
		]}
	/>
{/if}
