<script>
	/**
	 * A salon's customer list — staff-only (CLAUDE.md: a customer principal
	 * has no business reading another customer's record). Search is a plain
	 * name/phone substring match server-side (`listCustomers`'s `q`).
	 */
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { formatApiError } from '$lib/utils/errors.js';
	import { createCustomer, listCustomers } from '$lib/api/identity.js';
	import { resolve } from '$app/paths';

	import Icon from '$lib/components/ui/Icon.svelte';
	import Avatar from '$lib/components/ui/Avatar.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Pagination from '$lib/components/ui/Pagination.svelte';

	let tenantId = $derived(/** @type {string} */ (tenantStore.activeTenantId));

	let q = $state('');
	let offset = $state(0);
	const limit = 20;

	let loading = $state(true);
	let customers = $state(/** @type {import('$lib/api/identity.js').Customer[]} */ ([]));

	async function search() {
		loading = true;
		try {
			const page = await listCustomers(tenantId, { q: q || null, limit, offset });
			customers = page.items;
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		offset;
		search();
	});

	/** @param {SubmitEvent} event */
	function handleSearchSubmit(event) {
		event.preventDefault();
		offset = 0;
		search();
	}

	// --- Add customer ------------------------------------------------------------

	let addModalOpen = $state(false);
	let creating = $state(false);
	let createError = $state(/** @type {string|null} */ (null));
	let form = $state({ fullName: '', phone: '', email: '' });

	/** @param {SubmitEvent} event */
	async function handleCreate(event) {
		event.preventDefault();
		createError = null;
		creating = true;
		try {
			const customer = await createCustomer(tenantId, {
				fullName: form.fullName,
				phone: form.phone,
				email: form.email || null
			});
			customers = [customer, ...customers];
			addModalOpen = false;
			form = { fullName: '', phone: '', email: '' };
			toastStore.success('Customer added.');
		} catch (err) {
			createError = formatApiError(err);
		} finally {
			creating = false;
		}
	}
</script>

<svelte:head><title>Customers — NOVA</title></svelte:head>

<PageHeader
	eyebrow="Operate"
	title="Customers"
	subtitle="Everyone who has booked, or been added, at this business."
>
	{#snippet actions()}
		<Button onclick={() => (addModalOpen = true)}>
			<Icon name="plus" class="size-4" />
			Add customer
		</Button>
	{/snippet}
</PageHeader>

<form class="relative mb-6 max-w-md" onsubmit={handleSearchSubmit} role="search">
	<Icon
		name="search"
		class="pointer-events-none absolute start-3 top-1/2 z-10 size-4 -translate-y-1/2 text-fg-subtle"
	/>
	<Input
		placeholder="Search by name or phone"
		aria-label="Search customers"
		class="ps-9"
		bind:value={q}
	/>
</form>

{#if loading}
	<Card padding="none">
		<div class="divide-y divide-line-subtle">
			{#each [0, 1, 2, 3, 4] as n (n)}
				<div class="flex items-center gap-3 px-5 py-3.5">
					<Skeleton class="size-10 rounded-full" />
					<div class="flex-1 space-y-2">
						<Skeleton class="h-4 w-40" />
						<Skeleton class="h-3 w-28" />
					</div>
				</div>
			{/each}
		</div>
	</Card>
{:else if customers.length === 0}
	<EmptyState
		title={q ? 'No matches' : 'No customers yet'}
		description={q
			? 'Try a different name or phone number.'
			: "They'll show up here once they book, or you add them."}
	>
		{#snippet icon()}<Icon name="user" class="size-6" />{/snippet}
	</EmptyState>
{:else}
	<Card padding="none">
		<ul class="divide-y divide-line-subtle">
			{#each customers as customer (customer.id)}
				<li>
					<a
						href={resolve('/app/customers/[id]', { id: customer.id })}
						class="group duration-fast flex items-center gap-3 px-5 py-3.5 focus-ring transition-colors first:rounded-t-card last:rounded-b-card hover:bg-surface-sunken"
					>
						<Avatar name={customer.full_name} />
						<div class="min-w-0 flex-1">
							<p class="truncate text-sm font-medium text-fg">{customer.full_name}</p>
							<p class="truncate text-xs text-fg-muted">
								{[customer.phone, customer.email].filter(Boolean).join(' · ')}
							</p>
						</div>
						<Icon
							name="chevron-right"
							class="duration-fast size-4 text-fg-subtle transition-transform group-hover:translate-x-0.5 rtl:rotate-180"
						/>
					</a>
				</li>
			{/each}
		</ul>
	</Card>

	<div class="mt-4">
		<Pagination
			{limit}
			{offset}
			itemCount={customers.length}
			onchange={(next) => (offset = next)}
		/>
	</div>
{/if}

<Modal bind:open={addModalOpen} title="Add customer">
	{#if createError}
		<Alert tone="error" class="mb-4">{createError}</Alert>
	{/if}
	<form class="flex flex-col gap-4" onsubmit={handleCreate}>
		<Input label="Full name" required bind:value={form.fullName} />
		<div class="grid gap-4 sm:grid-cols-2">
			<Input type="tel" label="Phone" required bind:value={form.phone} />
			<Input type="email" label="Email" hint="Optional" bind:value={form.email} />
		</div>
		<Button type="submit" loading={creating} fullWidth>Add customer</Button>
	</form>
</Modal>
