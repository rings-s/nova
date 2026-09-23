<script>
	/**
	 * The staff dashboard shell. `tenant_id` for every call underneath comes
	 * from `tenantStore.activeTenantId` — set here once, read by every page in
	 * this section, never re-derived per page (CLAUDE.md: tenant_id is a URL
	 * path concern for the API, but the *client's* notion of "which business
	 * am I managing" lives in one place).
	 *
	 * Layout: a fixed sidebar (brand, business switcher, nav, account) from
	 * `lg` up; below that a slim top bar whose menu button opens the same
	 * sidebar as a drawer. The public SiteHeader stays out of /app entirely.
	 */
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { accessStore } from '$lib/stores/access.svelte.js';
	import { listMyTenants } from '$lib/api/identity.js';
	import { listBusinesses } from '$lib/api/catalog.js';
	import { businessStore } from '$lib/stores/business.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import ThemeToggle from '$lib/components/ui/ThemeToggle.svelte';
	import { iconButton } from '$lib/components/ui/styles.js';
	import DashboardNav from '$lib/components/layout/DashboardNav.svelte';
	import TenantSwitcher from '$lib/components/tenant/TenantSwitcher.svelte';
	import Logo from '$lib/components/layout/Logo.svelte';

	let { children } = $props();

	let resolvingTenant = $state(true);
	let resolvingBusiness = $state(true);

	// Which business this dashboard manages. Only registration and the catalog
	// form ever learn the id first-hand, so on any other device ask the API —
	// otherwise a salon that exists looks like one that doesn't, and every page
	// offers to "set up your storefront" again.
	$effect(() => {
		const tenantId = tenantStore.activeTenantId;
		if (!authStore.isStaff || !tenantId) return;
		if (businessStore.activeBusinessId) {
			resolvingBusiness = false;
			return;
		}
		let cancelled = false;
		resolvingBusiness = true;
		listBusinesses(tenantId)
			.then((page) => {
				if (!cancelled && page.items[0]) businessStore.set(tenantId, page.items[0].id);
			})
			// No business yet (or the lookup failed): the pages show their own
			// "set up your storefront" state, which is then the truth.
			.catch(() => {})
			.finally(() => {
				if (!cancelled) resolvingBusiness = false;
			});
		return () => {
			cancelled = true;
		};
	});
	let drawerOpen = $state(false);

	// This business's role, from its membership row — not the token's `roles`,
	// which merges every business the user works at.
	let roleLabel = $derived(
		accessStore.role
			? accessStore.role.replace(/^\w/, (c) => c.toUpperCase())
			: authStore.principal?.kind === 'service'
				? 'Service'
				: 'Staff'
	);

	$effect(() => {
		if (authStore.isStaff && tenantStore.activeTenantId) {
			accessStore.load(tenantStore.activeTenantId, String(authStore.principal?.sub ?? ''));
		}
	});

	$effect(() => {
		if (!authStore.isAuthenticated) {
			// Come back to this exact page after signing in.
			const next = encodeURIComponent(page.url.pathname + page.url.search);
			// eslint-disable-next-line svelte/no-navigation-without-resolve
			goto(`${resolve('/login')}?next=${next}`, { replaceState: true });
		} else if (!authStore.isStaff) {
			// A signed-in account without a business: most often an owner who
			// signed up as a customer. Offer to set one up rather than bouncing
			// them to the home page with no way forward.
			toastStore.info('Set up your business to use the dashboard.');
			goto(resolve('/business/new'), { replaceState: true });
		}
	});

	// Close the drawer on every navigation.
	$effect(() => {
		page.url.pathname;
		drawerOpen = false;
	});

	// A staff principal always has at least one membership (that's what makes
	// them staff) — this only fills in the id when the switcher hasn't
	// resolved one yet.
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

	async function signOut() {
		authStore.logout();
		toastStore.info('Signed out.');
		await goto(resolve('/'));
	}
</script>

<svelte:window
	onkeydown={(event) => drawerOpen && event.key === 'Escape' && (drawerOpen = false)}
/>

{#snippet sidebar()}
	<div class="flex h-full flex-col">
		<div class="flex h-16 shrink-0 items-center justify-between px-5">
			<a href={resolve('/')} class="rounded-control focus-ring" aria-label="NOVA home">
				<Logo />
			</a>
			<button
				type="button"
				class={`${iconButton} size-9 lg:hidden`}
				onclick={() => (drawerOpen = false)}
				aria-label="Close menu"
			>
				<Icon name="x" class="size-5" />
			</button>
		</div>

		<div class="px-4 pb-5">
			<p class="mb-1.5 px-1 text-[11px] font-semibold tracking-wider text-fg-subtle uppercase">
				Business
			</p>
			<TenantSwitcher />
		</div>

		<div class="min-h-0 flex-1 overflow-y-auto px-4 pb-6">
			<DashboardNav onnavigate={() => (drawerOpen = false)} />
		</div>

		<div class="shrink-0 border-t border-line p-3">
			<div class="flex items-center gap-2 rounded-control px-1 py-1.5">
				<span
					class="flex size-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent"
				>
					<Icon name="user" class="size-4" />
				</span>
				<div class="min-w-0 flex-1 leading-tight">
					<p class="truncate text-[13px] font-medium text-fg" title={roleLabel}>{roleLabel}</p>
					<a
						href={resolve('/discover')}
						class="inline-flex items-center gap-0.5 text-xs whitespace-nowrap text-fg-muted hover:text-accent"
					>
						Marketplace <Icon name="arrow-up-right" class="size-3 rtl:-scale-x-100" />
					</a>
				</div>
				<ThemeToggle />
				<button
					type="button"
					onclick={signOut}
					class={`${iconButton} size-9`}
					aria-label="Sign out"
					title="Sign out"
				>
					<Icon name="log-out" class="size-[18px] rtl:rotate-180" />
				</button>
			</div>
		</div>
	</div>
{/snippet}

{#if !authStore.isAuthenticated || !authStore.isStaff || resolvingTenant || resolvingBusiness || !accessStore.loaded}
	<div class="flex min-h-dvh items-center justify-center"><Spinner size="lg" /></div>
{:else}
	<div class="min-h-dvh lg:ps-64">
		<!-- Desktop sidebar -->
		<aside
			class="fixed inset-y-0 start-0 z-30 hidden w-64 border-e border-line bg-canvas lg:block dark:bg-slate-950"
		>
			{@render sidebar()}
		</aside>

		<!-- Mobile top bar -->
		<header
			class="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface/85 px-4 backdrop-blur-xl lg:hidden"
		>
			<button
				type="button"
				class={`${iconButton} -ms-1.5 size-9`}
				onclick={() => (drawerOpen = true)}
				aria-label="Open menu"
				aria-expanded={drawerOpen}
			>
				<Icon name="menu" class="size-5" />
			</button>
			<Logo />
			<div class="ms-auto"><ThemeToggle /></div>
		</header>

		<!-- Mobile drawer -->
		{#if drawerOpen}
			<div class="fixed inset-0 z-50 lg:hidden">
				<div
					class="absolute inset-0 animate-fade-in bg-slate-950/40 backdrop-blur-[2px]"
					onclick={() => (drawerOpen = false)}
					role="presentation"
				></div>
				<aside
					class="absolute inset-y-0 start-0 w-72 max-w-[85vw] animate-drawer-in border-e border-line bg-canvas shadow-overlay"
					aria-label="Menu"
				>
					{@render sidebar()}
				</aside>
			</div>
		{/if}

		<main class="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 sm:py-8 lg:px-10 lg:py-10">
			{@render children()}
		</main>
	</div>
{/if}
