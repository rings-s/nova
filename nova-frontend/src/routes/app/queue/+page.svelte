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

	import Icon from '$lib/components/ui/Icon.svelte';
	import Avatar from '$lib/components/ui/Avatar.svelte';
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

	/** @type {Record<string, string>} */
	const STATUS_LABEL = {
		waiting: 'Waiting',
		called: 'Called',
		checked_in: 'Checked in',
		in_service: 'In service',
		completed: 'Completed',
		missed: 'Missed',
		cancelled: 'Cancelled'
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
	let counts = $derived({
		waiting: entries.filter((e) => e.status === 'waiting').length,
		called: entries.filter((e) => e.status === 'called' || e.status === 'checked_in').length,
		serving: entries.filter((e) => e.status === 'in_service').length
	});
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

<PageHeader eyebrow="Operate" title="Walk-in queue" subtitle="Today's walk-in line." />

{#if !businessId}
	<Alert tone="info">Set up your storefront in Catalog first.</Alert>
{:else if loadingSetup}
	<div class="flex justify-center py-12"><Spinner /></div>
{:else if setupErrorMessage}
	<Alert tone="error">{setupErrorMessage}</Alert>
{:else if locations.length === 0}
	<EmptyState title="Add a location first" description="A queue belongs to one branch." />
{:else}
	<div class="mb-6 flex flex-wrap items-end gap-3">
		<div class="w-full sm:w-56">
			<Select
				label="Location"
				bind:value={selectedLocationId}
				options={locations.map((l) => ({ value: l.id, label: pickBilingual(l, 'name', 'en') }))}
			/>
		</div>
		{#if queues.length > 1}
			<div class="w-full sm:w-56">
				<Select
					label="Queue"
					bind:value={selectedQueueId}
					options={queues.map((q) => ({ value: q.id, label: pickBilingual(q, 'name', 'en') }))}
				/>
			</div>
		{/if}
	</div>

	{#if loadingQueues}
		<div class="flex justify-center py-8"><Spinner /></div>
	{:else if queues.length === 0}
		<EmptyState
			title="No queue at this location yet"
			description="Create one to start taking walk-ins and issuing tickets."
		>
			{#snippet icon()}<Icon name="users" class="size-6" />{/snippet}
			{#snippet action()}
				<Button loading={creatingQueue} onclick={handleCreateQueue}>
					<Icon name="plus" class="size-4" />
					Create queue
				</Button>
			{/snippet}
		</EmptyState>
	{:else}
		<!-- Control panel: queue state, live counts, and the two front-desk actions. -->
		<Card padding="none" class="mb-6 overflow-hidden">
			<div class="flex flex-wrap items-center justify-between gap-4 p-5">
				<div class="flex items-center gap-3">
					<span class="relative flex size-3">
						{#if selectedQueue?.is_open}
							<span
								class="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-60"
							></span>
						{/if}
						<span
							class={`relative inline-flex size-3 rounded-full ${selectedQueue?.is_open ? 'bg-emerald-500' : 'bg-fg-subtle'}`}
						></span>
					</span>
					<div>
						<p class="font-semibold text-fg">
							{selectedQueue ? pickBilingual(selectedQueue, 'name', 'en') : 'Queue'}
						</p>
						<p class="text-xs text-fg-muted">
							{selectedQueue?.is_open
								? 'Open — accepting walk-ins'
								: 'Closed — not accepting walk-ins'}
						</p>
					</div>
				</div>
				<div class="flex flex-wrap gap-2">
					{#if selectedQueue}
						<Button size="sm" variant="ghost" loading={togglingOpen} onclick={toggleOpen}>
							{selectedQueue.is_open ? 'Close queue' : 'Open queue'}
						</Button>
					{/if}
					<Button
						size="sm"
						variant="outline"
						disabled={services.length === 0}
						onclick={openAddModal}
					>
						<Icon name="plus" class="size-4" />
						Add walk-in
					</Button>
					<Button
						size="sm"
						loading={callingNext}
						disabled={!selectedQueue?.is_open}
						onclick={handleCallNext}
					>
						Call next
						<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
					</Button>
				</div>
			</div>
			<dl
				class="grid grid-cols-3 divide-x divide-line border-t border-line bg-surface-sunken rtl:divide-x-reverse"
			>
				{#each [{ label: 'Waiting', value: counts.waiting }, { label: 'Called', value: counts.called }, { label: 'In service', value: counts.serving }] as stat (stat.label)}
					<div class="px-5 py-3">
						<dt class="text-xs text-fg-muted">{stat.label}</dt>
						<dd class="text-xl font-semibold text-fg tabular-nums">
							{loadingEntries ? '—' : stat.value}
						</dd>
					</div>
				{/each}
			</dl>
		</Card>

		{#if loadingEntries}
			<div class="flex justify-center py-8"><Spinner /></div>
		{:else if entriesErrorMessage}
			<Alert tone="error">{entriesErrorMessage}</Alert>
		{:else if entries.length === 0}
			<EmptyState
				title="The line is empty"
				description="Walk-ins you add, or who join online, appear here."
			>
				{#snippet icon()}<Icon name="users" class="size-6" />{/snippet}
			</EmptyState>
		{:else}
			<Card padding="none">
				<ul class="divide-y divide-line-subtle">
					{#each entries as entry (entry.id)}
						{@const active = ['called', 'checked_in', 'in_service'].includes(entry.status)}
						<li
							class={`flex flex-wrap items-center justify-between gap-3 px-4 py-3.5 sm:px-5 ${active ? 'bg-accent-soft/50' : ''}`}
						>
							<div class="flex min-w-0 items-center gap-4">
								<span
									class={`flex size-11 shrink-0 items-center justify-center rounded-full text-sm font-semibold tabular-nums ${active ? 'bg-brand-600 text-white shadow-glow' : 'bg-surface-muted text-fg'}`}
								>
									{entry.place_in_line ?? entry.position}
								</span>
								<div class="min-w-0">
									<div class="flex flex-wrap items-center gap-2">
										<span class="text-sm font-semibold text-fg">
											{entry.place_in_line
												? `#${entry.place_in_line} in line`
												: `Position ${entry.position}`}
										</span>
										<Badge tone={STATUS_TONE[entry.status] ?? 'neutral'} size="sm" dot>
											{STATUS_LABEL[entry.status] ?? entry.status}
										</Badge>
									</div>
									<p class="mt-0.5 flex flex-wrap gap-x-3 text-xs text-fg-muted">
										{#if entry.joined_at}
											<span>Joined {formatRelative(entry.joined_at, 'en')}</span>
										{/if}
										{#if entry.party_size > 1}
											<span>Party of {entry.party_size}</span>
										{/if}
									</p>
								</div>
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
										<span class="text-xs text-fg-subtle">Scan their ticket to check in</span>
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
										variant="danger-ghost"
										loading={actingId === entry.id}
										onclick={() =>
											runEntryAction(entry.id, () => cancelQueueEntry(tenantId, entry.id))}
									>
										Remove
									</Button>
								{/if}
							</div>
						</li>
					{/each}
				</ul>
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
							class="flex items-center gap-3 rounded-control border border-line bg-surface px-3 py-2.5 text-start text-sm focus-ring transition-colors hover:border-line-strong hover:bg-surface-sunken"
							onclick={() => pickCustomer(customer)}
						>
							<Avatar name={customer.full_name} size="sm" />
							<span class="min-w-0 flex-1">
								<span class="block font-medium text-fg">{customer.full_name}</span>
								<span class="block text-xs text-fg-muted">{customer.phone}</span>
							</span>
							<Icon name="chevron-right" class="size-4 text-fg-subtle rtl:rotate-180" />
						</button>
					{/each}
				</div>
			{/if}
			<div class="mt-2 border-t border-line pt-4">
				<p class="mb-3 text-sm font-semibold text-fg">Or add a new customer</p>
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
			<p class="text-sm text-fg-secondary">
				Adding <strong>{selectedCustomer.full_name}</strong> to the line.
				<button
					type="button"
					class="text-accent hover:underline"
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
