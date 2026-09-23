<script>
	import { accessStore } from '$lib/stores/access.svelte.js';
	/**
	 * Catalog setup: locations, then the services and providers that hang off
	 * one location. A location must exist before either of the other two tabs
	 * means anything, so this defaults to — and pushes toward — that tab first.
	 */
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { businessStore } from '$lib/stores/business.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { formatApiError } from '$lib/utils/errors.js';
	import {
		createBusiness,
		createLocation,
		listLocations,
		setLocationPosition,
		createService,
		listServices,
		createProvider,
		listProviders,
		assignServiceToProvider
	} from '$lib/api/catalog.js';
	import { getProviderSchedule, setProviderSchedule } from '$lib/api/booking.js';
	import { pickBilingual } from '$lib/utils/bilingual.js';
	import { formatMinutesOfDay, parseMinutesOfDay, weekdayLabel } from '$lib/utils/datetime.js';

	import Icon from '$lib/components/ui/Icon.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import { fieldBase, fieldBorder } from '$lib/components/ui/styles.js';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Tabs from '$lib/components/ui/Tabs.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Checkbox from '$lib/components/ui/Checkbox.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import LocationCard from '$lib/components/catalog/LocationCard.svelte';
	import LocationPicker from '$lib/components/map/LocationPicker.svelte';
	import ServiceCard from '$lib/components/catalog/ServiceCard.svelte';
	import PhotoManager from '$lib/components/catalog/PhotoManager.svelte';
	import ProviderCard from '$lib/components/catalog/ProviderCard.svelte';

	// This page only ever renders inside `/app`'s layout, which does not render
	// its `children` until a tenant is selected.
	let tenantId = $derived(/** @type {string} */ (tenantStore.activeTenantId));
	let businessId = $derived(businessStore.activeBusinessId);
	// Owner and manager edit the catalog; everyone else reads it (and keeps the
	// rota — the Hours button stays open to all staff).
	let canEdit = $derived(accessStore.can('manage_catalog'));

	// --- Onboarding: a tenant with no cached business id yet ------------------

	let settingUpBusiness = $state(false);
	let businessNameEn = $state('');
	let businessNameAr = $state('');
	let setupError = $state(/** @type {string|null} */ (null));

	/** @param {SubmitEvent} event */
	async function handleCreateBusiness(event) {
		event.preventDefault();
		setupError = null;
		settingUpBusiness = true;
		try {
			const business = await createBusiness(tenantId, {
				nameEn: businessNameEn,
				nameAr: businessNameAr
			});
			businessStore.set(tenantId, business.id);
			toastStore.success('Storefront created.');
		} catch (err) {
			setupError = formatApiError(err);
		} finally {
			settingUpBusiness = false;
		}
	}

	// --- Locations --------------------------------------------------------------

	let activeTab = $state('locations');
	let locations = $state(/** @type {import('$lib/api/catalog.js').Location[]} */ ([]));
	let loadingLocations = $state(true);
	let locationModalOpen = $state(false);
	let creatingLocation = $state(false);
	let locationError = $state(/** @type {string|null} */ (null));
	let locationForm = $state({
		nameEn: '',
		nameAr: '',
		phone: '',
		city: '',
		latitude: /** @type {number|null} */ (null),
		longitude: /** @type {number|null} */ (null)
	});
	// True while the picker's coordinates field holds text that is not a position.
	let locationPinInvalid = $state(false);

	// Positioning a branch that already exists (one created before a pin could be
	// set, or one that has moved).
	let positionModalOpen = $state(false);
	let positionTarget = $state(/** @type {import('$lib/api/catalog.js').Location|null} */ (null));
	let positionForm = $state({
		latitude: /** @type {number|null} */ (null),
		longitude: /** @type {number|null} */ (null)
	});
	let positionPinInvalid = $state(false);
	let savingPosition = $state(false);
	let positionError = $state(/** @type {string|null} */ (null));

	let selectedLocationId = $state(/** @type {string|null} */ (null));

	async function loadLocations() {
		const currentBusinessId = businessId;
		if (!currentBusinessId) return;
		loadingLocations = true;
		try {
			const page = await listLocations(tenantId, currentBusinessId);
			locations = page.items;
			if (!selectedLocationId && locations[0]) selectedLocationId = locations[0].id;
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			loadingLocations = false;
		}
	}

	$effect(() => {
		if (businessId) loadLocations();
	});

	/** @param {SubmitEvent} event */
	async function handleCreateLocation(event) {
		event.preventDefault();
		locationError = null;
		creatingLocation = true;
		try {
			const location = await createLocation(tenantId, {
				businessId: /** @type {string} */ (businessId),
				nameEn: locationForm.nameEn,
				nameAr: locationForm.nameAr,
				phone: locationForm.phone,
				city: locationForm.city || null,
				latitude: locationForm.latitude,
				longitude: locationForm.longitude
			});
			locations = [...locations, location];
			selectedLocationId = location.id;
			locationModalOpen = false;
			locationForm = {
				nameEn: '',
				nameAr: '',
				phone: '',
				city: '',
				latitude: null,
				longitude: null
			};
			toastStore.success('Location added.');
		} catch (err) {
			locationError = formatApiError(err);
		} finally {
			creatingLocation = false;
		}
	}

	/** @param {import('$lib/api/catalog.js').Location} location */
	function openPositionModal(location) {
		positionTarget = location;
		positionForm = { latitude: location.latitude, longitude: location.longitude };
		positionError = null;
		positionModalOpen = true;
	}

	/** @param {SubmitEvent} event */
	async function handleSavePosition(event) {
		event.preventDefault();
		if (!positionTarget) return;
		positionError = null;
		savingPosition = true;
		try {
			const updated = await setLocationPosition(tenantId, positionTarget.id, {
				latitude: positionForm.latitude,
				longitude: positionForm.longitude
			});
			locations = locations.map((l) => (l.id === updated.id ? updated : l));
			positionModalOpen = false;
			toastStore.success(
				updated.latitude != null ? 'Map position saved.' : 'Branch removed from the map.'
			);
		} catch (err) {
			positionError = formatApiError(err);
		} finally {
			savingPosition = false;
		}
	}

	// --- Services ----------------------------------------------------------------

	let services = $state(/** @type {import('$lib/api/catalog.js').Service[]} */ ([]));
	let loadingServices = $state(false);
	let serviceModalOpen = $state(false);
	let creatingService = $state(false);
	let serviceError = $state(/** @type {string|null} */ (null));
	let serviceForm = $state({
		nameEn: '',
		nameAr: '',
		category: '',
		durationMinutes: 30,
		price: '',
		currency: 'SAR'
	});

	async function loadServices() {
		const currentLocationId = selectedLocationId;
		if (!currentLocationId) {
			services = [];
			return;
		}
		loadingServices = true;
		try {
			const page = await listServices(tenantId, currentLocationId);
			services = page.items;
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			loadingServices = false;
		}
	}

	$effect(() => {
		if (activeTab === 'services') loadServices();
	});

	/** @param {SubmitEvent} event */
	async function handleCreateService(event) {
		event.preventDefault();
		serviceError = null;
		creatingService = true;
		try {
			const service = await createService(tenantId, {
				locationId: /** @type {string} */ (selectedLocationId),
				nameEn: serviceForm.nameEn,
				nameAr: serviceForm.nameAr,
				category: serviceForm.category || null,
				durationMinutes: Number(serviceForm.durationMinutes),
				price: serviceForm.price,
				currency: serviceForm.currency
			});
			services = [...services, service];
			serviceModalOpen = false;
			serviceForm = {
				nameEn: '',
				nameAr: '',
				category: '',
				durationMinutes: 30,
				price: '',
				currency: 'SAR'
			};
			toastStore.success('Service added.');
		} catch (err) {
			serviceError = formatApiError(err);
		} finally {
			creatingService = false;
		}
	}

	// --- Providers ---------------------------------------------------------------

	let providers = $state(/** @type {import('$lib/api/catalog.js').Provider[]} */ ([]));
	let loadingProviders = $state(false);
	let providerModalOpen = $state(false);
	let creatingProvider = $state(false);
	let providerError = $state(/** @type {string|null} */ (null));
	let providerForm = $state({ nameEn: '', nameAr: '', titleEn: '' });

	let assignProviderId = $state('');
	let assignServiceId = $state('');
	let assigning = $state(false);

	async function loadProviders() {
		const currentLocationId = selectedLocationId;
		if (!currentLocationId) {
			providers = [];
			return;
		}
		loadingProviders = true;
		try {
			const page = await listProviders(tenantId, currentLocationId);
			providers = page.items;
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			loadingProviders = false;
		}
	}

	$effect(() => {
		if (activeTab === 'providers') {
			loadProviders();
			loadServices();
		}
	});

	/** @param {SubmitEvent} event */
	async function handleCreateProvider(event) {
		event.preventDefault();
		providerError = null;
		creatingProvider = true;
		try {
			const provider = await createProvider(tenantId, {
				locationId: /** @type {string} */ (selectedLocationId),
				nameEn: providerForm.nameEn,
				nameAr: providerForm.nameAr,
				titleEn: providerForm.titleEn || null
			});
			providers = [...providers, provider];
			providerModalOpen = false;
			providerForm = { nameEn: '', nameAr: '', titleEn: '' };
			toastStore.success('Provider added.');
		} catch (err) {
			providerError = formatApiError(err);
		} finally {
			creatingProvider = false;
		}
	}

	// --- Provider working hours --------------------------------------------------
	//
	// Availability has nothing to generate without this: `generate_availability`
	// (booking/domain.py) reads a provider's weekly windows, and a provider with
	// none simply has no bookable slots, ever.

	let scheduleModalOpen = $state(false);
	let scheduleProviderId = $state(/** @type {string|null} */ (null));
	let scheduleProviderName = $state('');
	let loadingSchedule = $state(false);
	let savingSchedule = $state(false);
	let scheduleError = $state(/** @type {string|null} */ (null));
	let scheduleHadSplitShifts = $state(false);

	function blankScheduleRows() {
		return Array.from({ length: 7 }, (_, weekday) => ({
			weekday,
			open: false,
			start: '09:00',
			end: '17:00'
		}));
	}

	let scheduleRows = $state(blankScheduleRows());

	/** @param {import('$lib/api/catalog.js').Provider} provider */
	async function openSchedule(provider) {
		scheduleProviderId = provider.id;
		scheduleProviderName = pickBilingual(provider, 'name', 'en');
		scheduleError = null;
		scheduleHadSplitShifts = false;
		scheduleModalOpen = true;
		loadingSchedule = true;
		scheduleRows = blankScheduleRows();
		try {
			const schedule = await getProviderSchedule(tenantId, provider.id);
			// A local, one-shot dedup scratchpad — never read by the template or
			// tracked across renders, so it doesn't need to be reactive.
			// eslint-disable-next-line svelte/prefer-svelte-reactivity
			const seenWeekdays = new Set();
			for (const window of schedule.windows) {
				if (seenWeekdays.has(window.weekday)) {
					scheduleHadSplitShifts = true;
					continue;
				}
				seenWeekdays.add(window.weekday);
				const row = scheduleRows[window.weekday];
				if (row) {
					row.open = true;
					row.start = formatMinutesOfDay(window.start_minute);
					row.end = formatMinutesOfDay(window.end_minute);
				}
			}
		} catch (err) {
			scheduleError = formatApiError(err);
		} finally {
			loadingSchedule = false;
		}
	}

	async function saveSchedule() {
		const providerId = scheduleProviderId;
		if (!providerId) return;
		scheduleError = null;
		savingSchedule = true;
		try {
			const windows = scheduleRows
				.filter((row) => row.open)
				.map((row) => ({
					weekday: row.weekday,
					start_minute: parseMinutesOfDay(row.start),
					end_minute: parseMinutesOfDay(row.end)
				}));
			await setProviderSchedule(tenantId, providerId, windows);
			scheduleModalOpen = false;
			toastStore.success('Working hours saved.');
		} catch (err) {
			scheduleError = formatApiError(err);
		} finally {
			savingSchedule = false;
		}
	}

	async function handleAssign() {
		if (!assignProviderId || !assignServiceId) return;
		assigning = true;
		try {
			await assignServiceToProvider(tenantId, assignProviderId, assignServiceId);
			toastStore.success('Service assigned.');
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			assigning = false;
		}
	}
</script>

<svelte:head><title>Catalog — NOVA</title></svelte:head>

{#snippet cardSkeletons()}
	<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
		{#each [0, 1, 2, 3] as n (n)}
			<div class="rounded-card border border-line bg-surface p-4 shadow-card">
				<div class="flex items-center gap-3">
					<Skeleton class="size-10 rounded-control" />
					<div class="flex-1 space-y-2">
						<Skeleton class="h-4 w-1/2" />
						<Skeleton class="h-3 w-1/3" />
					</div>
				</div>
			</div>
		{/each}
	</div>
{/snippet}

{#snippet locationFilter()}
	<div class="w-full sm:w-60">
		<Select
			label="Location"
			bind:value={selectedLocationId}
			options={locations.map((l) => ({
				value: l.id,
				label: pickBilingual(l, 'name', 'en')
			}))}
		/>
	</div>
{/snippet}

{#if !businessId}
	<PageHeader
		eyebrow="Business"
		title="Catalog"
		subtitle="Set up your storefront to start adding locations and services."
	/>
	{#if !canEdit}
		<Alert tone="info">The owner or a manager needs to set up the storefront first.</Alert>
	{:else}
		<Card padding="none" class="mx-auto max-w-xl overflow-hidden">
			<div class="border-b border-line bg-surface-sunken px-6 py-5">
				<div
					class="mb-3 flex size-11 items-center justify-center rounded-card text-white shadow-glow"
					style="background-image: var(--gradient-cta)"
				>
					<Icon name="sparkles" class="size-5" />
				</div>
				<h2 class="text-lg font-semibold tracking-tight text-fg">Create your storefront</h2>
				<p class="mt-1 text-sm text-fg-muted">
					Your business name appears on the marketplace in both English and Arabic.
				</p>
			</div>
			<div class="p-6">
				{#if setupError}
					<Alert tone="error" class="mb-4">{setupError}</Alert>
				{/if}
				<form class="flex flex-col gap-4" onsubmit={handleCreateBusiness}>
					<div class="grid gap-4 sm:grid-cols-2">
						<Input label="Business name (English)" required bind:value={businessNameEn} />
						<Input label="Business name (Arabic)" required dir="rtl" bind:value={businessNameAr} />
					</div>
					<Button type="submit" loading={settingUpBusiness} fullWidth>Create storefront</Button>
				</form>
			</div>
		</Card>
	{/if}
{:else}
	<PageHeader
		eyebrow="Business"
		title="Catalog"
		subtitle={canEdit
			? 'Locations, services and providers for this business.'
			: 'Locations, services and providers for this business. Only the owner or a manager can change them.'}
	/>

	<Tabs
		tabs={[
			{ id: 'locations', label: 'Locations', count: loadingLocations ? null : locations.length },
			{ id: 'services', label: 'Services' },
			{ id: 'providers', label: 'Providers' },
			{ id: 'photos', label: 'Photos' }
		]}
		bind:active={activeTab}
	/>

	<div class="mt-6">
		{#if activeTab === 'locations'}
			<div class="flex flex-col gap-4">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<p class="text-sm text-fg-muted">
						Each branch has its own services, providers, hours and map pin.
					</p>
					{#if canEdit}
						<Button size="sm" onclick={() => (locationModalOpen = true)}>
							<Icon name="plus" class="size-4" />
							Add location
						</Button>
					{/if}
				</div>
				{#if loadingLocations}
					{@render cardSkeletons()}
				{:else if locations.length === 0}
					<EmptyState title="No locations yet" description="Add your first branch to get started.">
						{#snippet icon()}<Icon name="building" class="size-6" />{/snippet}
					</EmptyState>
				{:else}
					<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
						{#each locations as location (location.id)}
							<LocationCard {location} onsetposition={canEdit ? openPositionModal : undefined} />
						{/each}
					</div>
				{/if}
			</div>
		{:else if activeTab === 'services'}
			{#if locations.length === 0}
				<EmptyState title="Add a location first" description="Services belong to one branch.">
					{#snippet icon()}<Icon name="building" class="size-6" />{/snippet}
				</EmptyState>
			{:else}
				<div class="flex flex-col gap-4">
					<div class="flex flex-wrap items-end justify-between gap-3">
						{@render locationFilter()}
						{#if canEdit}
							<Button
								size="sm"
								disabled={!selectedLocationId}
								onclick={() => (serviceModalOpen = true)}
							>
								<Icon name="plus" class="size-4" />
								Add service
							</Button>
						{/if}
					</div>
					{#if loadingServices}
						{@render cardSkeletons()}
					{:else if services.length === 0}
						<EmptyState title="No services yet" description="Add what this branch offers.">
							{#snippet icon()}<Icon name="sparkles" class="size-6" />{/snippet}
						</EmptyState>
					{:else}
						<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
							{#each services as service (service.id)}
								<ServiceCard {service} />
							{/each}
						</div>
					{/if}
				</div>
			{/if}
		{:else if activeTab === 'providers'}
			{#if locations.length === 0}
				<EmptyState title="Add a location first" description="Providers belong to one branch.">
					{#snippet icon()}<Icon name="building" class="size-6" />{/snippet}
				</EmptyState>
			{:else}
				<div class="flex flex-col gap-4">
					<div class="flex flex-wrap items-end justify-between gap-3">
						{@render locationFilter()}
						{#if canEdit}
							<Button
								size="sm"
								disabled={!selectedLocationId}
								onclick={() => (providerModalOpen = true)}
							>
								<Icon name="plus" class="size-4" />
								Add provider
							</Button>
						{/if}
					</div>
					{#if loadingProviders}
						{@render cardSkeletons()}
					{:else if providers.length === 0}
						<EmptyState title="No providers yet" description="Add who performs the work here.">
							{#snippet icon()}<Icon name="users" class="size-6" />{/snippet}
						</EmptyState>
					{:else}
						<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
							{#each providers as provider (provider.id)}
								<ProviderCard {provider}>
									{#snippet actions()}
										<Button size="sm" variant="outline" onclick={() => openSchedule(provider)}>
											<Icon name="clock" class="size-4" />
											Hours
										</Button>
									{/snippet}
								</ProviderCard>
							{/each}
						</div>

						{#if services.length > 0 && canEdit}
							<Card padding="none">
								{#snippet header()}
									<h2 class="text-sm font-semibold text-fg">Qualify a provider for a service</h2>
									<p class="mt-0.5 text-xs text-fg-muted">
										Customers can only book a provider for services they are qualified for.
									</p>
								{/snippet}
								<div class="flex flex-wrap items-end gap-3 p-5">
									<div class="w-full sm:w-52">
										<Select
											label="Provider"
											bind:value={assignProviderId}
											options={providers.map((p) => ({
												value: p.id,
												label: pickBilingual(p, 'name', 'en')
											}))}
										/>
									</div>
									<div class="w-full sm:w-52">
										<Select
											label="Service"
											bind:value={assignServiceId}
											options={services.map((s) => ({
												value: s.id,
												label: pickBilingual(s, 'name', 'en')
											}))}
										/>
									</div>
									<Button
										loading={assigning}
										disabled={!assignProviderId || !assignServiceId}
										onclick={handleAssign}
									>
										Assign
									</Button>
								</div>
							</Card>
						{/if}
					{/if}
				</div>
			{/if}
		{:else if activeTab === 'photos'}
			<PhotoManager {tenantId} businessId={businessId ?? ''} {canEdit} />
		{/if}
	</div>
{/if}

<Modal bind:open={locationModalOpen} title="Add location">
	{#if locationError}
		<Alert tone="error" class="mb-4">{locationError}</Alert>
	{/if}
	<form class="flex flex-col gap-4" onsubmit={handleCreateLocation}>
		<div class="grid gap-4 sm:grid-cols-2">
			<Input label="Name (English)" required bind:value={locationForm.nameEn} />
			<Input label="Name (Arabic)" required dir="rtl" bind:value={locationForm.nameAr} />
		</div>
		<Input type="tel" label="Phone" required bind:value={locationForm.phone} />
		<Input
			label="City"
			hint="Optional — used by marketplace search."
			bind:value={locationForm.city}
		/>
		<LocationPicker
			bind:latitude={locationForm.latitude}
			bind:longitude={locationForm.longitude}
			city={locationForm.city}
			onvalidity={(invalid) => (locationPinInvalid = invalid)}
		/>
		<Button type="submit" loading={creatingLocation} disabled={locationPinInvalid} fullWidth>
			Add location
		</Button>
	</form>
</Modal>

<Modal bind:open={positionModalOpen} title="Map position">
	{#if positionTarget}
		<p class="mb-3 text-sm text-fg-secondary">
			{pickBilingual(positionTarget, 'name', 'en')}
		</p>
	{/if}
	{#if positionError}
		<Alert tone="error" class="mb-4">{positionError}</Alert>
	{/if}
	<form class="flex flex-col gap-4" onsubmit={handleSavePosition}>
		<LocationPicker
			bind:latitude={positionForm.latitude}
			bind:longitude={positionForm.longitude}
			city={positionTarget?.city ?? null}
			onvalidity={(invalid) => (positionPinInvalid = invalid)}
		/>
		<Button type="submit" loading={savingPosition} disabled={positionPinInvalid} fullWidth>
			Save position
		</Button>
	</form>
</Modal>

<Modal bind:open={serviceModalOpen} title="Add service">
	{#if serviceError}
		<Alert tone="error" class="mb-4">{serviceError}</Alert>
	{/if}
	<form class="flex flex-col gap-4" onsubmit={handleCreateService}>
		<div class="grid gap-4 sm:grid-cols-2">
			<Input label="Name (English)" required bind:value={serviceForm.nameEn} />
			<Input label="Name (Arabic)" required dir="rtl" bind:value={serviceForm.nameAr} />
		</div>
		<Input label="Category" hint="Optional, e.g. Hair" bind:value={serviceForm.category} />
		<div class="grid gap-4 sm:grid-cols-2">
			<Input
				type="number"
				label="Duration (minutes)"
				required
				min="1"
				bind:value={serviceForm.durationMinutes}
			/>
			<Input
				type="number"
				label="Price"
				required
				min="0"
				step="0.01"
				bind:value={serviceForm.price}
			/>
		</div>
		<Button type="submit" loading={creatingService} fullWidth>Add service</Button>
	</form>
</Modal>

<Modal bind:open={providerModalOpen} title="Add provider">
	{#if providerError}
		<Alert tone="error" class="mb-4">{providerError}</Alert>
	{/if}
	<form class="flex flex-col gap-4" onsubmit={handleCreateProvider}>
		<div class="grid gap-4 sm:grid-cols-2">
			<Input label="Name (English)" required bind:value={providerForm.nameEn} />
			<Input label="Name (Arabic)" required dir="rtl" bind:value={providerForm.nameAr} />
		</div>
		<Input label="Title" hint="Optional, e.g. Senior Stylist" bind:value={providerForm.titleEn} />
		<Button type="submit" loading={creatingProvider} fullWidth>Add provider</Button>
	</form>
</Modal>

<Modal bind:open={scheduleModalOpen} title="Working hours — {scheduleProviderName}">
	{#if scheduleError}
		<Alert tone="error" class="mb-4">{scheduleError}</Alert>
	{/if}
	{#if scheduleHadSplitShifts}
		<Alert tone="warning" class="mb-4">
			This provider has a split shift (more than one window on the same day). Saving here keeps only
			one window per day and will collapse it.
		</Alert>
	{/if}
	{#if loadingSchedule}
		<div class="flex justify-center py-8"><Spinner /></div>
	{:else}
		<div class="flex flex-col gap-1">
			{#each scheduleRows as row (row.weekday)}
				<div
					class="flex items-center gap-3 rounded-control px-2 py-1.5 transition-colors hover:bg-surface-sunken"
				>
					<div class="w-28 shrink-0">
						<Checkbox label={weekdayLabel(row.weekday, 'en')} bind:checked={row.open} />
					</div>
					{#if row.open}
						<input
							type="time"
							aria-label={`${weekdayLabel(row.weekday, 'en')} opens`}
							bind:value={row.start}
							class={`${fieldBase} ${fieldBorder(false)} h-9 w-32`}
						/>
						<span class="text-sm text-fg-subtle" aria-hidden="true">–</span>
						<input
							type="time"
							aria-label={`${weekdayLabel(row.weekday, 'en')} closes`}
							bind:value={row.end}
							class={`${fieldBase} ${fieldBorder(false)} h-9 w-32`}
						/>
					{:else}
						<span class="text-sm text-fg-subtle">Closed</span>
					{/if}
				</div>
			{/each}
			<Button class="mt-2" loading={savingSchedule} fullWidth onclick={saveSchedule}
				>Save hours</Button
			>
		</div>
	{/if}
</Modal>
