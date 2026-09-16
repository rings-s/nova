<script>
	import { listMyTenants } from '../../api/identity.js';
	import { tenantStore } from '../../stores/tenant.svelte.js';
	import { toastStore } from '../../stores/toast.svelte.js';
	import { pickBilingual } from '../../utils/bilingual.js';
	import Select from '../ui/Select.svelte';
	import Spinner from '../ui/Spinner.svelte';

	/** @type {{ locale?: 'en'|'ar', onchange?: (tenantId: string) => void }} */
	let { locale = 'en', onchange } = $props();

	let tenants = $state(/** @type {import('../../api/identity.js').Tenant[]} */ ([]));
	let loading = $state(true);

	$effect(() => {
		let cancelled = false;
		loading = true;
		listMyTenants({ limit: 100 })
			.then((page) => {
				if (cancelled) return;
				tenants = page.items;
				if (!tenantStore.activeTenantId && tenants.length > 0) {
					tenantStore.set(tenants[0].id);
					onchange?.(tenants[0].id);
				}
			})
			.catch((err) => toastStore.fromError(err))
			.finally(() => {
				if (!cancelled) loading = false;
			});
		return () => {
			cancelled = true;
		};
	});

	/** @param {Event & { currentTarget: HTMLSelectElement }} event */
	function handleChange(event) {
		const tenantId = event.currentTarget.value;
		tenantStore.set(tenantId);
		onchange?.(tenantId);
	}
</script>

{#if loading}
	<Spinner size="sm" />
{:else if tenants.length === 0}
	<p class="text-sm text-slate-500 dark:text-slate-400">No businesses yet.</p>
{:else}
	<Select
		value={tenantStore.activeTenantId ?? ''}
		onchange={handleChange}
		options={tenants.map((tenant) => ({
			value: tenant.id,
			label: pickBilingual(tenant, 'name', locale)
		}))}
	/>
{/if}
