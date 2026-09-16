<script>
	/**
	 * The staff dashboard shell. `tenant_id` for every call underneath comes
	 * from `tenantStore.activeTenantId` — set here once, read by every page in
	 * this section, never re-derived per page (CLAUDE.md: tenant_id is a URL
	 * path concern for the API, but the *client's* notion of "which business
	 * am I managing" lives in one place).
	 */
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { listMyTenants } from '$lib/api/identity.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import DashboardNav from '$lib/components/layout/DashboardNav.svelte';

	let { children } = $props();

	let resolvingTenant = $state(true);

	$effect(() => {
		if (!authStore.isAuthenticated) {
			goto(resolve('/login'));
		} else if (!authStore.isStaff) {
			toastStore.info('That area is for business staff.');
			goto(resolve('/'));
		}
	});

	// A staff principal always has at least one membership (that's what makes
	// them staff) — this only fills in the id when the header's own switcher
	// hasn't resolved one yet.
	$effect(() => {
		if (!authStore.isStaff) return;
		if (tenantStore.activeTenantId) {
			resolvingTenant = false;
			return;
		}
		let cancelled = false;
		listMyTenants({ limit: 1 })
			.then((result) => {
				if (cancelled) return;
				if (result.items[0]) tenantStore.set(result.items[0].id);
			})
			.finally(() => {
				if (!cancelled) resolvingTenant = false;
			});
		return () => {
			cancelled = true;
		};
	});
</script>

{#if !authStore.isAuthenticated || !authStore.isStaff || resolvingTenant}
	<div class="flex justify-center py-24"><Spinner /></div>
{:else}
	<div class="mx-auto max-w-6xl px-4 py-8 sm:px-6">
		<div class="flex flex-col gap-6 lg:flex-row">
			<DashboardNav />
			<div class="min-w-0 flex-1">
				{@render children()}
			</div>
		</div>
	</div>
{/if}
