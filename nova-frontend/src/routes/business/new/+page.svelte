<script>
	/**
	 * Turns the signed-in account into a business owner: creates the business
	 * (tenant + storefront) with this account as its owner, then opens the
	 * dashboard.
	 *
	 * For anyone who signed up as a customer — often by not noticing the
	 * account-type choice — and then wants to list their salon. Without this,
	 * the only way to become an owner was a second account; the backend always
	 * allowed any account to create a business (`POST /tenants`), the app just
	 * never offered it.
	 */
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { businessStore } from '$lib/stores/business.svelte.js';
	import { accessStore } from '$lib/stores/access.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { createTenant } from '$lib/api/identity.js';
	import { createBusiness } from '$lib/api/catalog.js';
	import { formatApiError } from '$lib/utils/errors.js';

	import Container from '$lib/components/marketing/Container.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';

	let nameEn = $state('');
	let nameAr = $state('');
	let phone = $state('');
	let saving = $state(false);
	let error = $state(/** @type {string|null} */ (null));

	$effect(() => {
		if (!authStore.isAuthenticated) {
			// eslint-disable-next-line svelte/no-navigation-without-resolve
			goto(`${resolve('/login')}?next=${encodeURIComponent('/business/new')}`, {
				replaceState: true
			});
		}
	});

	/** @param {SubmitEvent} event */
	async function submit(event) {
		event.preventDefault();
		error = null;
		saving = true;
		try {
			const tenant = await createTenant({ nameEn, nameAr, phone });
			// The session was issued before this business existed, so it carries
			// no membership in it yet. Re-issue it so it does, then create the
			// storefront, which needs owner access.
			await authStore.refreshSession();
			const business = await createBusiness(tenant.id, { nameEn, nameAr });
			tenantStore.set(tenant.id);
			businessStore.set(tenant.id, business.id);
			accessStore.clear();
			toastStore.success(`${tenant.name_en} is on NOVA. Welcome to your dashboard.`);
			await goto(resolve('/app'));
		} catch (err) {
			error = formatApiError(err);
		} finally {
			saving = false;
		}
	}
</script>

<svelte:head><title>List your business — NOVA</title></svelte:head>

<Container size="md" class="py-12 sm:py-16">
	<div class="mx-auto max-w-xl">
		<p class="text-xs font-semibold tracking-wider text-accent uppercase">
			For salons, spas and clinics
		</p>
		<h1 class="mt-2 text-display-md font-semibold tracking-tight text-fg">List your business</h1>
		<p class="mt-2 text-fg-muted">
			Your account becomes the business owner, with the dashboard, bookings, walk-in queue and
			payments. You can add branches, services and your team next.
		</p>

		{#if authStore.isStaff}
			<Alert tone="info" class="mt-6">
				This account already runs a business.
				<a href={resolve('/app')} class="font-semibold text-accent hover:underline">
					Go to your dashboard
				</a>
			</Alert>
		{/if}

		<Card padding="lg" class="mt-8">
			<form class="flex flex-col gap-4" onsubmit={submit}>
				{#if error}
					<Alert tone="error">{error}</Alert>
				{/if}
				<div class="grid gap-4 sm:grid-cols-2">
					<Input label="Business name (English)" required bind:value={nameEn} />
					<Input label="Business name (Arabic)" required dir="rtl" bind:value={nameAr} />
				</div>
				<Input
					type="tel"
					label="Business phone"
					required
					hint="A GCC number customers can reach, e.g. +966 5X XXX XXXX."
					autocomplete="tel"
					bind:value={phone}
				/>
				<Button type="submit" size="lg" fullWidth loading={saving}>
					Create my business
					<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
				</Button>
			</form>
		</Card>
	</div>
</Container>
