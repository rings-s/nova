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

	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
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
	title="Customers"
	subtitle="Everyone who has booked, or been added, at this business."
/>

<div class="mb-4 flex flex-wrap items-end justify-between gap-3">
	<form class="min-w-0 flex-1" onsubmit={handleSearchSubmit}>
		<Input placeholder="Search by name or phone" bind:value={q} />
	</form>
	<Button onclick={() => (addModalOpen = true)}>Add customer</Button>
</div>

{#if loading}
	<div class="flex justify-center py-12"><Spinner /></div>
{:else if customers.length === 0}
	<EmptyState
		title="No customers yet"
		description="They'll show up here once they book, or you add them."
	/>
{:else}
	<Card padding="none">
		<div class="divide-y divide-slate-100 dark:divide-slate-800">
			{#each customers as customer (customer.id)}
				<a
					href={resolve('/app/customers/[id]', { id: customer.id })}
					class="flex items-center justify-between px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/50"
				>
					<div>
						<p class="text-sm font-medium text-slate-900 dark:text-slate-100">
							{customer.full_name}
						</p>
						<p class="text-xs text-slate-500 dark:text-slate-400">
							{[customer.phone, customer.email].filter(Boolean).join(' · ')}
						</p>
					</div>
				</a>
			{/each}
		</div>
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
		<Input type="tel" label="Phone" required bind:value={form.phone} />
		<Input type="email" label="Email" bind:value={form.email} />
		<Button type="submit" loading={creating} fullWidth>Add customer</Button>
	</form>
</Modal>
