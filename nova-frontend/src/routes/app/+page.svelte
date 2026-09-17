<script>
	import { resolve } from '$app/paths';
	import { businessStore } from '$lib/stores/business.svelte.js';
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { listBookings } from '$lib/api/booking.js';
	import { listServices, listProviders, listLocations } from '$lib/api/catalog.js';
	import { formatMoney } from '$lib/utils/money.js';
	import { formatDateTime } from '$lib/utils/datetime.js';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';

	let businessId = $derived(businessStore.activeBusinessId);
	let tenantId = $derived(/** @type {string|null} */ (tenantStore.activeTenantId));

	let loading = $state(true);
	let bookingCount = $state(0);
	let confirmedCount = $state(0);
	let serviceCount = $state(0);
	let providerCount = $state(0);
	let locationCount = $state(0);
	let recentBookings = $state(/** @type {import('$lib/api/booking.js').Booking[]} */ ([]));

	// Fetch a live operational summary. Services/providers are scoped per
	// location server-side (there's no single tenant-wide listing endpoint),
	// so this fetches the tenant's locations first, then aggregates across
	// them — rather than calling those endpoints with a missing id.
	$effect(() => {
		if (!tenantId || !businessId) {
			loading = false;
			return;
		}

		let cancelled = false;
		loading = true;

		async function load() {
			const [bookingsRes, locationsRes] = await Promise.all([
				listBookings(/** @type {string} */ (tenantId), { limit: 10 }).catch(() => ({ items: [] })),
				listLocations(/** @type {string} */ (tenantId), /** @type {string} */ (businessId)).catch(
					() => ({ items: [] })
				)
			]);
			if (cancelled) return;

			const items = bookingsRes?.items ?? [];
			recentBookings = items.slice(0, 4);
			bookingCount = items.length;
			confirmedCount = items.filter(
				(b) => b.status === 'confirmed' || b.status === 'in_service'
			).length;

			const locations = locationsRes?.items ?? [];
			locationCount = locations.length;

			const [servicesLists, providersLists] = await Promise.all([
				Promise.all(
					locations.map((loc) =>
						listServices(/** @type {string} */ (tenantId), loc.id).catch(() => ({ items: [] }))
					)
				),
				Promise.all(
					locations.map((loc) =>
						listProviders(/** @type {string} */ (tenantId), loc.id).catch(() => ({ items: [] }))
					)
				)
			]);
			if (cancelled) return;
			serviceCount = servicesLists.reduce((sum, res) => sum + (res?.items?.length ?? 0), 0);
			providerCount = providersLists.reduce((sum, res) => sum + (res?.items?.length ?? 0), 0);
		}

		load().finally(() => {
			if (!cancelled) loading = false;
		});

		return () => {
			cancelled = true;
		};
	});

	/**
	 * @type {{
	 *   title: string,
	 *   tag: string,
	 *   badge: string,
	 *   badgeTone: 'neutral'|'success'|'warning'|'error'|'info'|'accent',
	 *   icon: import('$lib/components/ui/Icon.svelte').IconName,
	 *   description: string,
	 *   href: '/app/queue'|'/app/bookings'|'/app/catalog'|'/app/billing'|'/app/team'|'/app/analytics'|'/app/customers'
	 * }[]}
	 */
	const modules = [
		{
			title: 'Queue & walk-ins',
			tag: 'Front desk',
			badge: 'Live',
			badgeTone: 'accent',
			icon: 'users',
			description: 'Manage the walk-in queue, issue tickets, and call the next customer.',
			href: '/app/queue'
		},
		{
			title: 'Bookings',
			tag: 'Schedule',
			badge: 'Deterministic holds',
			badgeTone: 'success',
			icon: 'calendar',
			description: "Today's day sheet — confirm, check in, and complete visits.",
			href: '/app/bookings'
		},
		{
			title: 'Catalog',
			tag: 'Services',
			badge: 'Bilingual',
			badgeTone: 'neutral',
			icon: 'sparkles',
			description: 'Manage locations, Arabic/English service menus, and providers.',
			href: '/app/catalog'
		},
		{
			title: 'Billing',
			tag: 'Finance',
			badge: 'Moyasar',
			badgeTone: 'success',
			icon: 'credit-card',
			description: 'Subscription, invoices, deposits and payouts.',
			href: '/app/billing'
		},
		{
			title: 'Team',
			tag: 'Access',
			badge: 'Role-based',
			badgeTone: 'neutral',
			icon: 'user-check',
			description: 'Invite staff and manage roles and permissions.',
			href: '/app/team'
		},
		{
			title: 'Analytics',
			tag: 'Reporting',
			badge: 'Charts',
			badgeTone: 'info',
			icon: 'chart-bar',
			description: 'Bookings, revenue and schedule breakdowns.',
			href: '/app/analytics'
		},
		{
			title: 'Customers',
			tag: 'Directory',
			badge: 'PDPL',
			badgeTone: 'neutral',
			icon: 'phone',
			description: 'Search your customer list and manage consent.',
			href: '/app/customers'
		}
	];
</script>

<svelte:head><title>Dashboard — NOVA</title></svelte:head>

<PageHeader title="Overview" subtitle="Your business at a glance." />

{#if !businessId}
	<Card padding="lg">
		<p class="text-slate-700 dark:text-slate-200">Set up your storefront to get started.</p>
		<Button class="mt-4" href={resolve('/app/catalog')}>Go to Catalog</Button>
	</Card>
{:else}
	<div class="space-y-8">
		<div class="grid grid-cols-2 gap-4 sm:grid-cols-4">
			<Card padding="md">
				<div class="flex items-center justify-between">
					<span class="text-xs font-semibold tracking-wide text-slate-500 uppercase">Bookings</span>
					<Icon name="calendar" class="size-4 text-brand-600 dark:text-brand-400" />
				</div>
				<p class="mt-2 text-2xl font-semibold text-slate-900 dark:text-slate-100">
					{#if loading}—{:else}{bookingCount}{/if}
				</p>
				<p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{confirmedCount} confirmed</p>
			</Card>

			<Card padding="md">
				<div class="flex items-center justify-between">
					<span class="text-xs font-semibold tracking-wide text-slate-500 uppercase">Providers</span
					>
					<Icon name="users" class="size-4 text-brand-600 dark:text-brand-400" />
				</div>
				<p class="mt-2 text-2xl font-semibold text-slate-900 dark:text-slate-100">
					{#if loading}—{:else}{providerCount}{/if}
				</p>
				<p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
					Across {locationCount || 1} location{locationCount === 1 ? '' : 's'}
				</p>
			</Card>

			<Card padding="md">
				<div class="flex items-center justify-between">
					<span class="text-xs font-semibold tracking-wide text-slate-500 uppercase">Services</span>
					<Icon name="sparkles" class="size-4 text-brand-600 dark:text-brand-400" />
				</div>
				<p class="mt-2 text-2xl font-semibold text-slate-900 dark:text-slate-100">
					{#if loading}—{:else}{serviceCount}{/if}
				</p>
				<p class="mt-1 text-xs text-slate-500 dark:text-slate-400">Arabic &amp; English</p>
			</Card>

			<Card padding="md">
				<div class="flex items-center justify-between">
					<span class="text-xs font-semibold tracking-wide text-slate-500 uppercase">Locations</span
					>
					<Icon name="globe" class="size-4 text-brand-600 dark:text-brand-400" />
				</div>
				<p class="mt-2 text-2xl font-semibold text-slate-900 dark:text-slate-100">
					{#if loading}—{:else}{locationCount}{/if}
				</p>
				<p class="mt-1 text-xs text-slate-500 dark:text-slate-400">Active branches</p>
			</Card>
		</div>

		<div>
			<h2 class="mb-3 text-xs font-semibold tracking-wide text-slate-500 uppercase">Sections</h2>
			<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
				{#each modules as mod (mod.href)}
					<a
						href={resolve(mod.href)}
						class="group flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-shadow hover:shadow-md dark:border-slate-800 dark:bg-slate-900"
					>
						<div>
							<div class="flex items-center justify-between">
								<div
									class="inline-flex size-9 items-center justify-center rounded-lg bg-brand-50 text-brand-600 dark:bg-brand-950/40 dark:text-brand-400"
								>
									<Icon name={mod.icon} class="size-5" />
								</div>
								<Badge tone={mod.badgeTone} size="sm">{mod.badge}</Badge>
							</div>
							<h3
								class="mt-3 font-semibold text-slate-900 group-hover:text-brand-600 dark:text-slate-100 dark:group-hover:text-brand-400"
							>
								{mod.title}
							</h3>
							<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">{mod.description}</p>
						</div>
						<div
							class="mt-4 flex items-center gap-1 text-sm font-medium text-brand-600 dark:text-brand-400"
						>
							<span>Open</span>
							<Icon
								name="arrow-right"
								class="size-4 transition-transform group-hover:translate-x-1"
							/>
						</div>
					</a>
				{/each}
			</div>
		</div>

		{#if recentBookings.length > 0}
			<Card padding="none">
				{#snippet header()}
					<div class="flex items-center justify-between">
						<h3 class="text-sm font-semibold text-slate-900 dark:text-slate-100">
							Recent bookings
						</h3>
						<Button href={resolve('/app/bookings')} variant="outline" size="sm"
							>View day sheet</Button
						>
					</div>
				{/snippet}
				<div class="divide-y divide-slate-100 dark:divide-slate-800">
					{#each recentBookings as booking (booking.id)}
						<div class="flex items-center justify-between px-5 py-3 text-sm">
							<span class="text-slate-700 dark:text-slate-300"
								>{formatDateTime(booking.starts_at, 'en')}</span
							>
							<div class="flex items-center gap-3">
								<span class="font-medium text-slate-900 dark:text-slate-100">
									{formatMoney(booking.price, booking.currency, 'en')}
								</span>
								<Badge tone={booking.status === 'confirmed' ? 'success' : 'neutral'} size="sm">
									{booking.status}
								</Badge>
							</div>
						</div>
					{/each}
				</div>
			</Card>
		{/if}
	</div>
{/if}
