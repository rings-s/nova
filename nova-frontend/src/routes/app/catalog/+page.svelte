<script>
	import { t, m } from '$lib/i18n/index.svelte.js';
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
		assignServiceToProvider,
		updateLocation,
		deleteLocation,
		updateService,
		deleteService,
		updateProvider,
		deleteProvider
	} from '$lib/api/catalog.js';
	import { getProviderSchedule, setProviderSchedule } from '$lib/api/booking.js';
	import { listCategories } from '$lib/api/discovery.js';
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
			toastStore.success(t('Storefront created.'));
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
				city: '',
				latitude: null,
				longitude: null
			};
			toastStore.success(t('Location added.'));
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
				updated.latitude != null ? t('Map position saved.') : t('Branch removed from the map.')
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
		categoryId: '',
		durationMinutes: 30,
		price: '',
		currency: 'SAR'
	});

	// The platform's category list: only a NOVA administrator adds to it, so a
	// salon picks from it rather than typing its own.
	let categories = $state(/** @type {import('$lib/api/catalog.js').Category[]} */ ([]));
	let categoriesLoaded = false;

	$effect(() => {
		if (serviceModalOpen) loadCategories();
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
				categoryId: serviceForm.categoryId || null,
				durationMinutes: Number(serviceForm.durationMinutes),
				price: serviceForm.price,
				currency: serviceForm.currency
			});
			services = [...services, service];
			serviceModalOpen = false;
			serviceForm = {
				nameEn: '',
				nameAr: '',
				categoryId: '',
				durationMinutes: 30,
				price: '',
				currency: 'SAR'
			};
			toastStore.success(t('Service added.'));
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
			toastStore.success(t('Provider added.'));
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
		scheduleProviderName = pickBilingual(provider, 'name');
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
			toastStore.success(t('Working hours saved.'));
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
			toastStore.success(t('Service assigned.'));
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			assigning = false;
		}
	}

	// --- Edit and delete ------------------------------------------------------

	/**
	 * The one open edit dialog: which kind of row, which row, and its draft.
	 * @typedef {{ kind: 'location', item: import('$lib/api/catalog.js').Location }
	 *   | { kind: 'service', item: import('$lib/api/catalog.js').Service }
	 *   | { kind: 'provider', item: import('$lib/api/catalog.js').Provider }} CatalogRow
	 */
	let editing = $state(/** @type {CatalogRow|null} */ (null));
	let editOpen = $state(false);
	let editForm = $state({
		nameEn: '',
		nameAr: '',
		city: '',
		titleEn: '',
		titleAr: '',
		categoryId: '',
		durationMinutes: 30,
		price: '',
		isActive: true
	});
	let savingEdit = $state(false);
	let editError = $state(/** @type {string|null} */ (null));

	let deleting = $state(/** @type {CatalogRow|null} */ (null));
	let deleteOpen = $state(false);
	let removingRow = $state(false);

	/** @param {CatalogRow} row */
	function openEdit(row) {
		const item = /** @type {Record<string, any>} */ (row.item);
		editForm = {
			nameEn: item.name_en,
			nameAr: item.name_ar,
			city: item.city ?? '',
			titleEn: item.title_en ?? '',
			titleAr: item.title_ar ?? '',
			categoryId: item.category_id ?? '',
			durationMinutes: item.duration_minutes ?? 30,
			price: item.price ?? '',
			isActive: item.is_active
		};
		if (row.kind === 'service') loadCategories();
		editError = null;
		editing = row;
		editOpen = true;
	}

	// Loaded the first time a service dialog (add or edit) opens.
	function loadCategories() {
		if (categoriesLoaded) return;
		categoriesLoaded = true;
		listCategories()
			.then((rows) => (categories = rows))
			.catch((err) => {
				categoriesLoaded = false;
				toastStore.fromError(err);
			});
	}

	/** @param {SubmitEvent} event */
	async function handleSaveEdit(event) {
		event.preventDefault();
		if (!editing) return;
		editError = null;
		savingEdit = true;
		const common = {
			nameEn: editForm.nameEn,
			nameAr: editForm.nameAr,
			isActive: editForm.isActive
		};
		try {
			if (editing.kind === 'location') {
				const updated = await updateLocation(tenantId, editing.item.id, {
					...common,
					city: editForm.city || null
				});
				locations = locations.map((l) => (l.id === updated.id ? updated : l));
			} else if (editing.kind === 'service') {
				const updated = await updateService(tenantId, editing.item.id, {
					...common,
					categoryId: editForm.categoryId || null,
					durationMinutes: Number(editForm.durationMinutes),
					price: editForm.price
				});
				services = services.map((s) => (s.id === updated.id ? updated : s));
			} else {
				const updated = await updateProvider(tenantId, editing.item.id, {
					...common,
					titleEn: editForm.titleEn || null,
					titleAr: editForm.titleAr || null
				});
				providers = providers.map((p) => (p.id === updated.id ? updated : p));
			}
			editOpen = false;
			toastStore.success(t('Changes saved.'));
		} catch (err) {
			editError = formatApiError(err);
		} finally {
			savingEdit = false;
		}
	}

	/** @param {CatalogRow} row */
	function askDelete(row) {
		deleting = row;
		deleteOpen = true;
	}

	async function handleDelete() {
		if (!deleting) return;
		removingRow = true;
		const { kind, item } = deleting;
		try {
			if (kind === 'location') {
				await deleteLocation(tenantId, item.id);
				locations = locations.filter((l) => l.id !== item.id);
				if (selectedLocationId === item.id) selectedLocationId = locations[0]?.id ?? null;
			} else if (kind === 'service') {
				await deleteService(tenantId, item.id);
				services = services.filter((s) => s.id !== item.id);
			} else {
				await deleteProvider(tenantId, item.id);
				providers = providers.filter((p) => p.id !== item.id);
			}
			deleteOpen = false;
			toastStore.success(t('Deleted.'));
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			removingRow = false;
		}
	}

	const EDIT_TITLES = {
		location: m('Edit location'),
		service: m('Edit service'),
		provider: m('Edit provider')
	};
	const DELETE_WARNINGS = {
		location: m('Its services and providers are deleted with it.'),
		service: m('Customers can no longer book it.'),
		provider: m('Customers can no longer book them.')
	};
</script>

<svelte:head><title>{t('Catalog')} — NOVA</title></svelte:head>

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
			label={t('Location')}
			bind:value={selectedLocationId}
			options={locations.map((l) => ({
				value: l.id,
				label: pickBilingual(l, 'name')
			}))}
		/>
	</div>
{/snippet}

{#if !businessId}
	<PageHeader
		eyebrow={t('Business')}
		title={t('Catalog')}
		subtitle={t('Set up your storefront to start adding locations and services.')}
	/>
	{#if !canEdit}
		<Alert tone="info">{t('The owner or a manager needs to set up the storefront first.')}</Alert>
	{:else}
		<Card padding="none" class="mx-auto max-w-xl overflow-hidden">
			<div class="border-b border-line bg-surface-sunken px-6 py-5">
				<div
					class="mb-3 flex size-11 items-center justify-center rounded-card text-white shadow-glow"
					style="background-image: var(--gradient-cta)"
				>
					<Icon name="sparkles" class="size-5" />
				</div>
				<h2 class="text-lg font-semibold tracking-tight text-fg">{t('Create your storefront')}</h2>
				<p class="mt-1 text-sm text-fg-muted">
					{t('Your business name appears on the marketplace in both English and Arabic.')}
				</p>
			</div>
			<div class="p-6">
				{#if setupError}
					<Alert tone="error" class="mb-4">{setupError}</Alert>
				{/if}
				<form class="flex flex-col gap-4" onsubmit={handleCreateBusiness}>
					<div class="grid gap-4 sm:grid-cols-2">
						<Input label={t('Business name (English)')} required bind:value={businessNameEn} />
						<Input
							label={t('Business name (Arabic)')}
							required
							dir="rtl"
							bind:value={businessNameAr}
						/>
					</div>
					<Button type="submit" loading={settingUpBusiness} fullWidth
						>{t('Create storefront')}</Button
					>
				</form>
			</div>
		</Card>
	{/if}
{:else}
	<PageHeader
		eyebrow={t('Business')}
		title={t('Catalog')}
		subtitle={canEdit
			? t('Locations, services and providers for this business.')
			: t(
					'Locations, services and providers for this business. Only the owner or a manager can change them.'
				)}
	/>

	<Tabs
		tabs={[
			{ id: 'locations', label: t('Locations'), count: loadingLocations ? null : locations.length },
			{ id: 'services', label: t('Services') },
			{ id: 'providers', label: t('Providers') },
			{ id: 'photos', label: t('Photos') }
		]}
		bind:active={activeTab}
	/>

	<div class="mt-6">
		{#if activeTab === 'locations'}
			<div class="flex flex-col gap-4">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<p class="text-sm text-fg-muted">
						{t('Each branch has its own services, providers, hours and map pin.')}
					</p>
					{#if canEdit}
						<Button size="sm" onclick={() => (locationModalOpen = true)}>
							<Icon name="plus" class="size-4" />
							{t('Add location')}
						</Button>
					{/if}
				</div>
				{#if loadingLocations}
					{@render cardSkeletons()}
				{:else if locations.length === 0}
					<EmptyState
						title={t('No locations yet')}
						description={t('Add your first branch to get started.')}
					>
						{#snippet icon()}<Icon name="building" class="size-6" />{/snippet}
					</EmptyState>
				{:else}
					<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
						{#each locations as location (location.id)}
							<LocationCard
								{location}
								onsetposition={canEdit ? openPositionModal : undefined}
								onedit={canEdit ? (item) => openEdit({ kind: 'location', item }) : undefined}
								ondelete={canEdit ? (item) => askDelete({ kind: 'location', item }) : undefined}
							/>
						{/each}
					</div>
				{/if}
			</div>
		{:else if activeTab === 'services'}
			{#if locations.length === 0}
				<EmptyState
					title={t('Add a location first')}
					description={t('Services belong to one branch.')}
				>
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
								{t('Add service')}
							</Button>
						{/if}
					</div>
					{#if loadingServices}
						{@render cardSkeletons()}
					{:else if services.length === 0}
						<EmptyState
							title={t('No services yet')}
							description={t('Add what this branch offers.')}
						>
							{#snippet icon()}<Icon name="sparkles" class="size-6" />{/snippet}
						</EmptyState>
					{:else}
						<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
							{#each services as service (service.id)}
								{#if canEdit}
									<ServiceCard {service}>
										{#snippet actions()}
											<Button
												size="sm"
												variant="ghost"
												onclick={() => openEdit({ kind: 'service', item: service })}
											>
												{t('Edit')}
											</Button>
											<Button
												size="sm"
												variant="danger-ghost"
												onclick={() => askDelete({ kind: 'service', item: service })}
											>
												{t('Delete')}
											</Button>
										{/snippet}
									</ServiceCard>
								{:else}
									<ServiceCard {service} />
								{/if}
							{/each}
						</div>
					{/if}
				</div>
			{/if}
		{:else if activeTab === 'providers'}
			{#if locations.length === 0}
				<EmptyState
					title={t('Add a location first')}
					description={t('Providers belong to one branch.')}
				>
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
								{t('Add provider')}
							</Button>
						{/if}
					</div>
					{#if loadingProviders}
						{@render cardSkeletons()}
					{:else if providers.length === 0}
						<EmptyState
							title={t('No providers yet')}
							description={t('Add who performs the work here.')}
						>
							{#snippet icon()}<Icon name="users" class="size-6" />{/snippet}
						</EmptyState>
					{:else}
						<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
							{#each providers as provider (provider.id)}
								<ProviderCard {provider}>
									{#snippet actions()}
										<Button size="sm" variant="outline" onclick={() => openSchedule(provider)}>
											<Icon name="clock" class="size-4" />
											{t('Hours')}
										</Button>
										{#if canEdit}
											<Button
												size="icon-sm"
												variant="ghost"
												aria-label={t('Edit')}
												onclick={() => openEdit({ kind: 'provider', item: provider })}
											>
												<Icon name="settings" class="size-4" />
											</Button>
											<Button
												size="icon-sm"
												variant="danger-ghost"
												aria-label={t('Delete')}
												onclick={() => askDelete({ kind: 'provider', item: provider })}
											>
												<Icon name="x" class="size-4" />
											</Button>
										{/if}
									{/snippet}
								</ProviderCard>
							{/each}
						</div>

						{#if services.length > 0 && canEdit}
							<Card padding="none">
								{#snippet header()}
									<h2 class="text-sm font-semibold text-fg">
										{t('Qualify a provider for a service')}
									</h2>
									<p class="mt-0.5 text-xs text-fg-muted">
										{t('Customers can only book a provider for services they are qualified for.')}
									</p>
								{/snippet}
								<div class="flex flex-wrap items-end gap-3 p-5">
									<div class="w-full sm:w-52">
										<Select
											label={t('Provider')}
											bind:value={assignProviderId}
											options={providers.map((p) => ({
												value: p.id,
												label: pickBilingual(p, 'name')
											}))}
										/>
									</div>
									<div class="w-full sm:w-52">
										<Select
											label={t('Service')}
											bind:value={assignServiceId}
											options={services.map((s) => ({
												value: s.id,
												label: pickBilingual(s, 'name')
											}))}
										/>
									</div>
									<Button
										loading={assigning}
										disabled={!assignProviderId || !assignServiceId}
										onclick={handleAssign}
									>
										{t('Assign')}
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

<Modal bind:open={locationModalOpen} title={t('Add location')}>
	{#if locationError}
		<Alert tone="error" class="mb-4">{locationError}</Alert>
	{/if}
	<form class="flex flex-col gap-4" onsubmit={handleCreateLocation}>
		<div class="grid gap-4 sm:grid-cols-2">
			<Input label={t('Name (English)')} required bind:value={locationForm.nameEn} />
			<Input label={t('Name (Arabic)')} required dir="rtl" bind:value={locationForm.nameAr} />
		</div>
		<Input
			label={t('City')}
			hint={t('Optional — used by marketplace search.')}
			bind:value={locationForm.city}
		/>
		<LocationPicker
			bind:latitude={locationForm.latitude}
			bind:longitude={locationForm.longitude}
			city={locationForm.city}
			onvalidity={(invalid) => (locationPinInvalid = invalid)}
		/>
		<Button type="submit" loading={creatingLocation} disabled={locationPinInvalid} fullWidth>
			{t('Add location')}
		</Button>
	</form>
</Modal>

<Modal bind:open={positionModalOpen} title={t('Map position')}>
	{#if positionTarget}
		<p class="mb-3 text-sm text-fg-secondary">
			{pickBilingual(positionTarget, 'name')}
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
			{t('Save position')}
		</Button>
	</form>
</Modal>

<Modal bind:open={serviceModalOpen} title={t('Add service')}>
	{#if serviceError}
		<Alert tone="error" class="mb-4">{serviceError}</Alert>
	{/if}
	<form class="flex flex-col gap-4" onsubmit={handleCreateService}>
		<div class="grid gap-4 sm:grid-cols-2">
			<Input label={t('Name (English)')} required bind:value={serviceForm.nameEn} />
			<Input label={t('Name (Arabic)')} required dir="rtl" bind:value={serviceForm.nameAr} />
		</div>
		<Select
			label={t('Category')}
			hint={t('Optional. Categories are set by NOVA for every business.')}
			bind:value={serviceForm.categoryId}
			options={[
				{ value: '', label: t('No category') },
				...categories.map((c) => ({ value: c.id, label: pickBilingual(c, 'name') }))
			]}
		/>
		<div class="grid gap-4 sm:grid-cols-2">
			<Input
				type="number"
				label={t('Duration (minutes)')}
				required
				min="1"
				bind:value={serviceForm.durationMinutes}
			/>
			<Input
				type="number"
				label={t('Price')}
				required
				min="0"
				step="0.01"
				bind:value={serviceForm.price}
			/>
		</div>
		<Button type="submit" loading={creatingService} fullWidth>{t('Add service')}</Button>
	</form>
</Modal>

<Modal bind:open={providerModalOpen} title={t('Add provider')}>
	{#if providerError}
		<Alert tone="error" class="mb-4">{providerError}</Alert>
	{/if}
	<form class="flex flex-col gap-4" onsubmit={handleCreateProvider}>
		<div class="grid gap-4 sm:grid-cols-2">
			<Input label={t('Name (English)')} required bind:value={providerForm.nameEn} />
			<Input label={t('Name (Arabic)')} required dir="rtl" bind:value={providerForm.nameAr} />
		</div>
		<Input
			label={t('Title')}
			hint={t('Optional, e.g. Senior Stylist')}
			bind:value={providerForm.titleEn}
		/>
		<Button type="submit" loading={creatingProvider} fullWidth>{t('Add provider')}</Button>
	</form>
</Modal>

<Modal
	bind:open={scheduleModalOpen}
	title={t('Working hours — {name}', { name: scheduleProviderName })}
>
	{#if scheduleError}
		<Alert tone="error" class="mb-4">{scheduleError}</Alert>
	{/if}
	{#if scheduleHadSplitShifts}
		<Alert tone="warning" class="mb-4">
			{t(
				'This provider has a split shift (more than one window on the same day). Saving here keeps only one window per day and will collapse it.'
			)}
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
						<Checkbox label={weekdayLabel(row.weekday)} bind:checked={row.open} />
					</div>
					{#if row.open}
						<input
							type="time"
							aria-label={t('{day} opens', { day: weekdayLabel(row.weekday) })}
							bind:value={row.start}
							class={`${fieldBase} ${fieldBorder(false)} h-9 w-32`}
						/>
						<span class="text-sm text-fg-subtle" aria-hidden="true">–</span>
						<input
							type="time"
							aria-label={t('{day} closes', { day: weekdayLabel(row.weekday) })}
							bind:value={row.end}
							class={`${fieldBase} ${fieldBorder(false)} h-9 w-32`}
						/>
					{:else}
						<span class="text-sm text-fg-subtle">{t('Closed')}</span>
					{/if}
				</div>
			{/each}
			<Button class="mt-2" loading={savingSchedule} fullWidth onclick={saveSchedule}
				>{t('Save hours')}</Button
			>
		</div>
	{/if}
</Modal>

<Modal bind:open={editOpen} title={editing ? t(EDIT_TITLES[editing.kind]) : ''}>
	{#if editError}
		<Alert tone="error" class="mb-4">{editError}</Alert>
	{/if}
	{#if editing}
		<form class="flex flex-col gap-4" onsubmit={handleSaveEdit}>
			<div class="grid gap-4 sm:grid-cols-2">
				<Input label={t('Name (English)')} required bind:value={editForm.nameEn} />
				<Input label={t('Name (Arabic)')} required dir="rtl" bind:value={editForm.nameAr} />
			</div>
			{#if editing.kind === 'location'}
				<Input
					label={t('City')}
					hint={t('Optional — used by marketplace search.')}
					bind:value={editForm.city}
				/>
			{:else if editing.kind === 'service'}
				<Select
					label={t('Category')}
					bind:value={editForm.categoryId}
					options={[
						{ value: '', label: t('No category') },
						...categories.map((c) => ({ value: c.id, label: pickBilingual(c, 'name') }))
					]}
				/>
				<div class="grid gap-4 sm:grid-cols-2">
					<Input
						type="number"
						label={t('Duration (minutes)')}
						required
						min="1"
						bind:value={editForm.durationMinutes}
					/>
					<Input
						type="number"
						label={t('Price')}
						required
						min="0"
						step="0.01"
						bind:value={editForm.price}
					/>
				</div>
				<p class="text-xs text-fg-muted">
					{t('Bookings already made keep the price and time they were made with.')}
				</p>
			{:else}
				<div class="grid gap-4 sm:grid-cols-2">
					<Input label={t('Title (English)')} bind:value={editForm.titleEn} />
					<Input label={t('Title (Arabic)')} dir="rtl" bind:value={editForm.titleAr} />
				</div>
			{/if}
			<div>
				<Checkbox label={t('Taking bookings')} bind:checked={editForm.isActive} />
				<p class="ms-7 mt-1 text-xs text-fg-muted">
					{t('Switch off to stop new bookings without deleting anything.')}
				</p>
			</div>
			<Button type="submit" loading={savingEdit} fullWidth>{t('Save changes')}</Button>
		</form>
	{/if}
</Modal>

<Modal
	bind:open={deleteOpen}
	title={t('Delete {name}?', { name: deleting ? pickBilingual(deleting.item, 'name') : '' })}
>
	{#if deleting}
		<p class="text-sm text-fg-muted">{t(DELETE_WARNINGS[deleting.kind])}</p>
		<p class="mt-2 text-sm text-fg-muted">
			{t('Past bookings keep their record. Anything with an upcoming booking cannot be deleted.')}
		</p>
		<div class="mt-5 flex justify-end gap-2">
			<Button variant="ghost" onclick={() => (deleteOpen = false)}>{t('Cancel')}</Button>
			<Button variant="danger" loading={removingRow} onclick={handleDelete}>{t('Delete')}</Button>
		</div>
	{/if}
</Modal>
