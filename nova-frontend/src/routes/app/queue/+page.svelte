<script>
	/**
	 * The live walk-in line for one location. There is deliberately no manual
	 * "check in" endpoint (queue/router.py) — CALLED only becomes CHECKED_IN by
	 * redeeming a ticket's QR (docs/09 #8), which the customer's phone or the
	 * front-desk ticket holds. For a walk-in this page adds itself, the ticket
	 * is issued immediately and its payload kept in memory just long enough to
	 * redeem it with one click — a stand-in for a camera scan, not a shortcut
	 * around the backend's rule (see `ticketsByEntry` below). A queue entry
	 * this dashboard didn't add gets no such shortcut; staff scan its QR the
	 * normal way.
	 */
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { businessStore } from '$lib/stores/business.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { errorMessage, formatApiError } from '$lib/utils/errors.js';
	import { pickBilingual } from '$lib/utils/bilingual.js';
	import { formatRelative } from '$lib/utils/datetime.js';
	import { listLocations, listServices, listProviders } from '$lib/api/catalog.js';
	import { listCustomers, createCustomer } from '$lib/api/identity.js';
	import {
		listQueues,
		createQueue,
		setQueueOpen,
		listQueueEntries,
		joinQueue,
		callNext,
		markMissed,
		requeue,
		startQueueService,
		completeQueueEntry,
		cancelQueueEntry,
		issueTicket,
		checkInWithTicket
	} from '$lib/api/queue.js';

	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';

	let tenantId = $derived(/** @type {string} */ (tenantStore.activeTenantId));
	let businessId = $derived(businessStore.activeBusinessId);

	/** @type {Record<string, 'neutral'|'success'|'warning'|'error'|'info'|'accent'>} */
	const STATUS_TONE = {
		waiting: 'info',
		called: 'accent',
		checked_in: 'accent',
		in_service: 'accent',
		completed: 'success',
		missed: 'warning',
		cancelled: 'neutral'
	};

	let locations = $state(/** @type {import('$lib/api/catalog.js').Location[]} */ ([]));
	let selectedLocationId = $state(/** @type {string} */ (''));
	let services = $state(/** @type {import('$lib/api/catalog.js').Service[]} */ ([]));
	let providers = $state(/** @type {import('$lib/api/catalog.js').Provider[]} */ ([]));

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

	let queues = $state(/** @type {import('$lib/api/queue.js').Queue[]} */ ([]));
	let selectedQueueId = $state(/** @type {string} */ (''));
	let loadingQueues = $state(false);
	let creatingQueue = $state(false);

	async function loadQueuesAndCatalog() {
		const locationId = selectedLocationId;
		if (!locationId) return;
		loadingQueues = true;
		try {
			const [queuesPage, servicesPage, providersPage] = await Promise.all([
				listQueues(tenantId, locationId),
				listServices(tenantId, locationId),
				listProviders(tenantId, locationId)
			]);
			queues = queuesPage.items;
			services = servicesPage.items;
			providers = providersPage.items;
			if (!queues.some((q) => q.id === selectedQueueId)) {
				selectedQueueId = queues[0]?.id ?? '';
			}
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			loadingQueues = false;
		}
	}

	$effect(() => {
		if (selectedLocationId) loadQueuesAndCatalog();
	});

	async function handleCreateQueue() {
		creatingQueue = true;
		try {
			const queue = await createQueue(tenantId, { locationId: selectedLocationId });
			queues = [...queues, queue];
			selectedQueueId = queue.id;
			toastStore.success('Queue created.');
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			creatingQueue = false;
		}
	}

	let selectedQueue = $derived(queues.find((q) => q.id === selectedQueueId) ?? null);
	let togglingOpen = $state(false);

	async function toggleOpen() {
		if (!selectedQueue) return;
		togglingOpen = true;
		try {
			const updated = await setQueueOpen(tenantId, selectedQueue.id, !selectedQueue.is_open);
			queues = queues.map((q) => (q.id === updated.id ? updated : q));
			toastStore.success(updated.is_open ? 'Queue opened.' : 'Queue closed.');
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			togglingOpen = false;
		}
	}

	// --- The live line ------------------------------------------------------------

	let entries = $state(/** @type {import('$lib/api/queue.js').QueueEntry[]} */ ([]));
	let loadingEntries = $state(false);
	let entriesErrorMessage = $state(/** @type {string|null} */ (null));

	/** Tickets this page itself issued, held only long enough for the one-tap
	 * check-in described above. @type {Record<string, string>} entryId -> qr_payload */
	let ticketsByEntry = $state({});

	async function loadEntries() {
		const queueId = selectedQueueId;
		if (!queueId) {
			entries = [];
			return;
		}
		loadingEntries = true;
		entriesErrorMessage = null;
		try {
			const page = await listQueueEntries(tenantId, queueId, { limit: 50 });
			entries = page.items;
		} catch (err) {
			entriesErrorMessage = errorMessage(err);
		} finally {
			loadingEntries = false;
		}
	}

	$effect(() => {
		if (selectedQueueId) loadEntries();
	});

	// Poll while a queue is selected, so the board reflects other terminals too.
	$effect(() => {
		if (!selectedQueueId) return;
		const interval = setInterval(loadEntries, 15000);
		return () => clearInterval(interval);
	});

	/** @param {import('$lib/api/queue.js').QueueEntry} updated */
	function applyEntryUpdate(updated) {
		entries = entries.map((e) => (e.id === updated.id ? updated : e));
	}

	let actingId = $state(/** @type {string|null} */ (null));

	/** @param {string} entryId @param {() => Promise<import('$lib/api/queue.js').QueueEntry>} action */
	async function runEntryAction(entryId, action) {
		actingId = entryId;
		try {
			applyEntryUpdate(await action());
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			actingId = null;
		}
	}

	let callingNext = $state(false);

	async function handleCallNext() {
		if (!selectedQueueId) return;
		callingNext = true;
		try {
			const entry = await callNext(tenantId, selectedQueueId);
			const exists = entries.some((e) => e.id === entry.id);
			entries = exists ? entries.map((e) => (e.id === entry.id ? entry : e)) : [...entries, entry];
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			callingNext = false;
		}
	}

	/** @param {import('$lib/api/queue.js').QueueEntry} entry */
	async function handleCheckIn(entry) {
		const qrPayload = ticketsByEntry[entry.id];
		if (!qrPayload) return;
		actingId = entry.id;
		try {
			const result = await checkInWithTicket(tenantId, qrPayload);
			if (result.entry) applyEntryUpdate(result.entry);
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			actingId = null;
		}
	}

	// --- Add walk-in -----------------------------------------------------------

	let addModalOpen = $state(false);
	let addStep = $state(/** @type {'customer'|'details'} */ ('customer'));
	let customerQuery = $state('');
	let customerResults = $state(/** @type {import('$lib/api/identity.js').Customer[]} */ ([]));
	let searchingCustomers = $state(false);
	let selectedCustomer = $state(/** @type {import('$lib/api/identity.js').Customer|null} */ (null));
	let newCustomerForm = $state({ fullName: '', phone: '' });
	let creatingCustomer = $state(false);
	let joinForm = $state({ serviceId: '', providerId: '', partySize: 1 });
	let joining = $state(false);
	let addError = $state(/** @type {string|null} */ (null));

	function openAddModal() {
		addStep = 'customer';
		customerQuery = '';
		customerResults = [];
		selectedCustomer = null;
		newCustomerForm = { fullName: '', phone: '' };
		joinForm = { serviceId: services[0]?.id ?? '', providerId: '', partySize: 1 };
		addError = null;
		addModalOpen = true;
	}

	async function searchCustomers() {
		if (!customerQuery.trim()) {
			customerResults = [];
			return;
		}
		searchingCustomers = true;
		try {
			const page = await listCustomers(tenantId, { q: customerQuery, limit: 10 });
			customerResults = page.items;
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			searchingCustomers = false;
		}
	}

	/** @param {KeyboardEvent} event */
	function handleCustomerQueryKeydown(event) {
		if (event.key === 'Enter') searchCustomers();
	}

	/** @param {import('$lib/api/identity.js').Customer} customer */
	function pickCustomer(customer) {
		selectedCustomer = customer;
		addStep = 'details';
	}

	/** @param {SubmitEvent} event */
	async function handleCreateCustomer(event) {
		event.preventDefault();
		addError = null;
		creatingCustomer = true;
		try {
			const customer = await createCustomer(tenantId, {
				fullName: newCustomerForm.fullName,
				phone: newCustomerForm.phone
			});
			pickCustomer(customer);
		} catch (err) {
			addError = formatApiError(err);
		} finally {
			creatingCustomer = false;
		}
	}

	/** @param {SubmitEvent} event */
	async function handleJoin(event) {
		event.preventDefault();
		if (!selectedCustomer || !selectedQueueId) return;
		addError = null;
		joining = true;
		try {
			const entry = await joinQueue(tenantId, selectedQueueId, {
				serviceId: joinForm.serviceId,
				providerId: joinForm.providerId || null,
				partySize: Number(joinForm.partySize),
				onBehalfOfCustomerId: selectedCustomer.id
			});
			entries = [...entries, entry];
			try {
				const ticket = await issueTicket(tenantId, { queueEntryId: entry.id });
				ticketsByEntry = { ...ticketsByEntry, [entry.id]: ticket.qr_payload };
			} catch {
				// The entry is still valid without a ticket — staff can issue one
				// later, or the customer can be checked in by other means.
			}
			addModalOpen = false;
			toastStore.success(`${selectedCustomer.full_name} added to the queue.`);
		} catch (err) {
			addError = formatApiError(err);
		} finally {
			joining = false;
		}
	}
</script>

<svelte:head><title>Queue — NOVA</title></svelte:head>

<PageHeader title="Queue" subtitle="Today's walk-in line." />

{#if !businessId}
	<Alert tone="info">Set up your storefront in Catalog first.</Alert>
{:else if loadingSetup}
	<div class="flex justify-center py-12"><Spinner /></div>
{:else if setupErrorMessage}
	<Alert tone="error">{setupErrorMessage}</Alert>
{:else if locations.length === 0}
	<EmptyState title="Add a location first" description="A queue belongs to one branch." />
{:else}
	<div class="mb-4 flex flex-wrap items-end justify-between gap-3">
		<div class="flex flex-wrap items-end gap-3">
			<div class="w-full max-w-xs">
				<Select
					label="Location"
					bind:value={selectedLocationId}
					options={locations.map((l) => ({ value: l.id, label: pickBilingual(l, 'name', 'en') }))}
				/>
			</div>
			{#if queues.length > 0}
				<div class="w-full max-w-xs">
					<Select
						label="Queue"
						bind:value={selectedQueueId}
						options={queues.map((q) => ({ value: q.id, label: pickBilingual(q, 'name', 'en') }))}
					/>
				</div>
			{/if}
		</div>
		{#if selectedQueue}
			<div class="flex items-center gap-2">
				<Badge tone={selectedQueue.is_open ? 'success' : 'neutral'}>
					{selectedQueue.is_open ? 'Open' : 'Closed'}
				</Badge>
				<Button size="sm" variant="outline" loading={togglingOpen} onclick={toggleOpen}>
					{selectedQueue.is_open ? 'Close queue' : 'Open queue'}
				</Button>
			</div>
		{/if}
	</div>

	{#if loadingQueues}
		<div class="flex justify-center py-8"><Spinner /></div>
	{:else if queues.length === 0}
		<EmptyState title="No queue at this location yet">
			{#snippet action()}
				<Button loading={creatingQueue} onclick={handleCreateQueue}>Create queue</Button>
			{/snippet}
		</EmptyState>
	{:else}
		<div class="mb-4 flex justify-between gap-2">
			<Button loading={callingNext} disabled={!selectedQueue?.is_open} onclick={handleCallNext}>
				Call next
			</Button>
			<Button variant="outline" disabled={services.length === 0} onclick={openAddModal}>
				Add walk-in
			</Button>
		</div>

		{#if loadingEntries}
			<div class="flex justify-center py-8"><Spinner /></div>
		{:else if entriesErrorMessage}
			<Alert tone="error">{entriesErrorMessage}</Alert>
		{:else if entries.length === 0}
			<EmptyState title="The line is empty" />
		{:else}
			<Card padding="none">
				<div class="divide-y divide-slate-100 dark:divide-slate-800">
					{#each entries as entry (entry.id)}
						<div class="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
							<div class="min-w-0">
								<div class="flex items-center gap-2">
									<span class="text-sm font-medium text-slate-900 dark:text-slate-100">
										{entry.place_in_line ? `#${entry.place_in_line}` : `Position ${entry.position}`}
									</span>
									<Badge tone={STATUS_TONE[entry.status] ?? 'neutral'}>{entry.status}</Badge>
									{#if entry.party_size > 1}
										<span class="text-xs text-slate-500 dark:text-slate-400"
											>Party of {entry.party_size}</span
										>
									{/if}
								</div>
								{#if entry.joined_at}
									<p class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
										Joined {formatRelative(entry.joined_at, 'en')}
									</p>
								{/if}
							</div>
							<div class="flex flex-wrap items-center gap-2">
								{#if entry.status === 'called'}
									{#if ticketsByEntry[entry.id]}
										<Button
											size="sm"
											loading={actingId === entry.id}
											onclick={() => handleCheckIn(entry)}
										>
											Check in
										</Button>
									{:else}
										<span class="text-xs text-slate-400">Scan their ticket to check in</span>
									{/if}
									<Button
										size="sm"
										variant="outline"
										loading={actingId === entry.id}
										onclick={() => runEntryAction(entry.id, () => markMissed(tenantId, entry.id))}
									>
										Missed
									</Button>
								{/if}
								{#if entry.status === 'checked_in'}
									<Button
										size="sm"
										loading={actingId === entry.id}
										onclick={() =>
											runEntryAction(entry.id, () => startQueueService(tenantId, entry.id))}
									>
										Start service
									</Button>
								{/if}
								{#if entry.status === 'in_service'}
									<Button
										size="sm"
										loading={actingId === entry.id}
										onclick={() =>
											runEntryAction(entry.id, () => completeQueueEntry(tenantId, entry.id))}
									>
										Complete
									</Button>
								{/if}
								{#if entry.status === 'missed'}
									<Button
										size="sm"
										variant="outline"
										loading={actingId === entry.id}
										onclick={() => runEntryAction(entry.id, () => requeue(tenantId, entry.id))}
									>
										Requeue
									</Button>
								{/if}
								{#if entry.status === 'waiting' || entry.status === 'called'}
									<Button
										size="sm"
										variant="danger"
										loading={actingId === entry.id}
										onclick={() =>
											runEntryAction(entry.id, () => cancelQueueEntry(tenantId, entry.id))}
									>
										Remove
									</Button>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			</Card>
		{/if}
	{/if}
{/if}

<Modal bind:open={addModalOpen} title="Add walk-in">
	{#if addError}
		<Alert tone="error" class="mb-4">{addError}</Alert>
	{/if}
	{#if addStep === 'customer'}
		<div class="flex flex-col gap-3">
			<div class="flex gap-2">
				<div class="flex-1">
					<Input
						placeholder="Search by name or phone"
						bind:value={customerQuery}
						onkeydown={handleCustomerQueryKeydown}
					/>
				</div>
				<Button loading={searchingCustomers} onclick={searchCustomers}>Search</Button>
			</div>
			{#if customerResults.length > 0}
				<div class="flex flex-col gap-1">
					{#each customerResults as customer (customer.id)}
						<button
							type="button"
							class="rounded-lg border border-slate-200 px-3 py-2 text-left text-sm hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50"
							onclick={() => pickCustomer(customer)}
						>
							<span class="font-medium text-slate-900 dark:text-slate-100"
								>{customer.full_name}</span
							>
							<span class="text-slate-500 dark:text-slate-400"> · {customer.phone}</span>
						</button>
					{/each}
				</div>
			{/if}
			<div class="border-t border-slate-200 pt-3 dark:border-slate-800">
				<p class="mb-2 text-sm font-medium text-slate-700 dark:text-slate-200">
					Or add a new customer
				</p>
				<form class="flex flex-col gap-3" onsubmit={handleCreateCustomer}>
					<Input label="Full name" required bind:value={newCustomerForm.fullName} />
					<Input type="tel" label="Phone" required bind:value={newCustomerForm.phone} />
					<Button type="submit" variant="outline" loading={creatingCustomer}>
						Add and continue
					</Button>
				</form>
			</div>
		</div>
	{:else if selectedCustomer}
		<form class="flex flex-col gap-4" onsubmit={handleJoin}>
			<p class="text-sm text-slate-600 dark:text-slate-300">
				Adding <strong>{selectedCustomer.full_name}</strong> to the line.
				<button
					type="button"
					class="text-brand-600 hover:underline dark:text-brand-400"
					onclick={() => (addStep = 'customer')}
				>
					Change
				</button>
			</p>
			<Select
				label="Service"
				required
				bind:value={joinForm.serviceId}
				options={services.map((s) => ({ value: s.id, label: pickBilingual(s, 'name', 'en') }))}
			/>
			{#if providers.length > 0}
				<Select
					label="Preferred provider"
					hint="Optional — leave unset for the next available."
					bind:value={joinForm.providerId}
					options={providers.map((p) => ({ value: p.id, label: pickBilingual(p, 'name', 'en') }))}
				/>
			{/if}
			<Input type="number" label="Party size" min="1" max="20" bind:value={joinForm.partySize} />
			<Button type="submit" loading={joining} fullWidth disabled={!joinForm.serviceId}>
				Add to queue
			</Button>
		</form>
	{/if}
</Modal>
