<script>
	import { resolve } from '$app/paths';
	import { businessStore } from '$lib/stores/business.svelte.js';
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { accessStore } from '$lib/stores/access.svelte.js';

	import { listProviderCalendar } from '$lib/api/booking.js';
	import { listServices, listProviders, listLocations } from '$lib/api/catalog.js';

	import { formatMoney } from '$lib/utils/money.js';
	import { formatTime } from '$lib/utils/datetime.js';

	import Card from '$lib/components/ui/Card.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import StatCard from '$lib/components/ui/StatCard.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import BookingStatusBadge from '$lib/components/booking/BookingStatusBadge.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';

	let businessId = $derived(businessStore.activeBusinessId);
	let tenantId = $derived(/** @type {string|null} */ (tenantStore.activeTenantId));

	let loading = $state(true);

	let bookingCount = $state(0);
	let confirmedCount = $state(0);
	let serviceCount = $state(0);
	let providerCount = $state(0);
	let locationCount = $state(0);

	/** @type {import('$lib/api/booking.js').Booking[]} */
	let recentBookings = $state([]);

	/**
	 * @type {{
	 *   title: string,
	 *   icon: import('$lib/components/ui/Icon.svelte').IconName,
	 *   description: string,
	 *   href: '/app/queue'|'/app/bookings'|'/app/catalog'|'/app/billing'|'/app/team'|'/app/analytics'|'/app/customers',
	 *   needs?: import('$lib/api/identity.js').StaffPermission
	 * }[]}
	 */
	const shortcuts = [
		{
			title: 'Walk-in queue',
			icon: 'users',
			description: 'Issue tickets and call the next customer.',
			href: '/app/queue'
		},
		{
			title: 'Day sheet',
			icon: 'calendar',
			description: 'Confirm, check in and complete visits.',
			href: '/app/bookings'
		},
		{
			title: 'Catalog',
			icon: 'layers',
			description: 'Locations, bilingual services and providers.',
			href: '/app/catalog'
		},
		{
			title: 'Customers',
			icon: 'user',
			description: 'Search your customers and manage consent.',
			href: '/app/customers'
		},
		{
			title: 'Analytics',
			icon: 'chart-bar',
			description: 'Bookings, revenue and utilization.',
			href: '/app/analytics',
			needs: 'view_analytics'
		},
		{
			title: 'Billing',
			icon: 'credit-card',
			description: 'Subscription, invoices and payouts.',
			href: '/app/billing',
			needs: 'view_financials'
		},
		{
			title: 'Team',
			icon: 'user-check',
			description: 'Who works here, and at what role.',
			href: '/app/team'
		}
	];

	const greeting = (() => {
		const hour = new Date().getHours();
		return hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
	})();

	/**
	 * Load dashboard data for the active tenant.
	 */
	$effect(() => {
		if (!tenantId || !businessId) {
			loading = false;
			return;
		}

		const tenant = tenantId;
		const business = businessId;
		let cancelled = false;

		loading = true;

		async function loadDashboard() {
			/** @type {import('$lib/api/catalog.js').Location[]} */
			const locations = (await listLocations(tenant, business).catch(() => ({ items: [] }))).items;
			if (cancelled) return;
			locationCount = locations.length;

			const [serviceResponses, providerResponses] = await Promise.all([
				Promise.all(
					locations.map((location) =>
						listServices(tenant, location.id).catch(() => ({ items: [] }))
					)
				),
				Promise.all(
					locations.map((location) =>
						listProviders(tenant, location.id).catch(() => ({ items: [] }))
					)
				)
			]);
			if (cancelled) return;

			serviceCount = serviceResponses.reduce((total, r) => total + (r?.items?.length ?? 0), 0);
			const providers = providerResponses.flatMap((r) => r?.items ?? []);
			providerCount = providers.length;

			// Today's appointments, from each provider's day sheet: the staff view
			// of bookings. (`GET /bookings` is a customer's own history and has
			// nothing to say to a staff account.)
			const now = new Date();
			const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
			const end = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
			const range = { dateFrom: start.toISOString(), dateTo: end.toISOString() };
			const calendars = await Promise.all(
				providers.map((provider) =>
					listProviderCalendar(tenant, provider.id, range).catch(() => ({ items: [] }))
				)
			);
			if (cancelled) return;

			/** @type {import('$lib/api/booking.js').Booking[]} */
			const today = calendars
				.flatMap((calendar) => calendar.items)
				.filter((booking) => booking.status !== 'cancelled')
				.sort((x, y) => new Date(x.starts_at).getTime() - new Date(y.starts_at).getTime());

			bookingCount = today.length;
			confirmedCount = today.filter((booking) =>
				['confirmed', 'checked_in', 'in_service', 'completed'].includes(booking.status)
			).length;
			// What is still ahead today, soonest first; the rest of the day if
			// nothing is.
			const ahead = today.filter((booking) => new Date(booking.ends_at).getTime() >= now.getTime());
			recentBookings = (ahead.length ? ahead : today).slice(0, 5);
		}

		loadDashboard().finally(() => {
			if (!cancelled) {
				loading = false;
			}
		});

		return () => {
			cancelled = true;
		};
	});
</script>

<svelte:head>
	<title>Dashboard — NOVA</title>
</svelte:head>

<PageHeader eyebrow="Overview" title={greeting} subtitle="Here's how your business looks today.">
	{#snippet actions()}
		<Button variant="outline" href={resolve('/app/bookings')}>
			<Icon name="calendar" class="size-4" />
			Day sheet
		</Button>
		<Button href={resolve('/app/queue')}>
			<Icon name="users" class="size-4" />
			Open queue
		</Button>
	{/snippet}
</PageHeader>

{#if !businessId}
	<Card padding="lg" class="overflow-hidden">
		<div class="flex flex-col gap-5 sm:flex-row sm:items-center">
			<div
				class="flex size-12 shrink-0 items-center justify-center rounded-card text-white shadow-glow"
				style="background-image: var(--gradient-cta)"
			>
				<Icon name="sparkles" class="size-6" />
			</div>
			<div class="flex-1">
				<h2 class="text-lg font-semibold tracking-tight text-fg">Set up your storefront</h2>
				<p class="mt-1 text-sm text-fg-muted">
					Add a location, your services and your staff before you start accepting bookings.
				</p>
			</div>
			<Button href={resolve('/app/catalog')}>
				Go to catalog
				<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
			</Button>
		</div>
	</Card>
{:else}
	<div class="space-y-8">
		<section class="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4" aria-label="Key numbers">
			<StatCard
				label="Today"
				icon="calendar"
				{loading}
				value={bookingCount}
				hint={`${confirmedCount} confirmed or underway`}
				href={resolve('/app/bookings')}
			/>
			<StatCard
				label="Providers"
				icon="users"
				{loading}
				value={providerCount}
				hint={`Across ${locationCount} location${locationCount === 1 ? '' : 's'}`}
			/>
			<StatCard
				label="Services"
				icon="sparkles"
				{loading}
				value={serviceCount}
				hint="Arabic & English"
			/>
			<StatCard
				label="Locations"
				icon="map-pin"
				{loading}
				value={locationCount}
				hint="Active branches"
				href={resolve('/app/catalog')}
			/>
		</section>

		<div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
			<Card padding="none">
				{#snippet header()}
					<div class="flex items-center justify-between gap-4">
						<div>
							<h2 class="font-semibold text-fg">Today's appointments</h2>
							<p class="mt-0.5 text-xs text-fg-muted">Next up across your providers</p>
						</div>
						<Button href={resolve('/app/bookings')} variant="ghost" size="sm">
							View all
							<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
						</Button>
					</div>
				{/snippet}

				{#if loading}
					<div class="divide-y divide-line-subtle">
						{#each [0, 1, 2] as row (row)}
							<div class="flex items-center justify-between gap-4 px-5 py-4">
								<Skeleton class="h-4 w-40" />
								<Skeleton class="h-5 w-20 rounded-full" />
							</div>
						{/each}
					</div>
				{:else if recentBookings.length === 0}
					<div class="p-5">
						<EmptyState
							title="Nothing booked today"
							description="New appointments will appear here as customers book."
						>
							{#snippet icon()}<Icon name="calendar" class="size-6" />{/snippet}
						</EmptyState>
					</div>
				{:else}
					<ul class="divide-y divide-line-subtle">
						{#each recentBookings as booking (booking.id)}
							<li class="flex items-center justify-between gap-4 px-5 py-3.5">
								<div class="flex min-w-0 items-center gap-3">
									<span
										class="flex size-9 shrink-0 items-center justify-center rounded-control bg-surface-muted text-fg-muted"
									>
										<Icon name="clock" class="size-4" />
									</span>
									<p class="truncate text-sm font-medium text-fg">
										{formatTime(booking.starts_at, 'en')} – {formatTime(booking.ends_at, 'en')}
									</p>
								</div>
								<div class="flex shrink-0 items-center gap-3">
									<span class="text-sm font-medium text-fg tabular-nums">
										{formatMoney(booking.price, booking.currency, 'en')}
									</span>
									<BookingStatusBadge status={booking.status} />
								</div>
							</li>
						{/each}
					</ul>
				{/if}
			</Card>

			<section aria-labelledby="shortcuts-heading">
				<h2 id="shortcuts-heading" class="mb-3 text-sm font-semibold text-fg">Shortcuts</h2>
				<ul class="overflow-hidden rounded-card border border-line bg-surface shadow-card">
					{#each shortcuts.filter((item) => !item.needs || accessStore.can(item.needs)) as item (item.href)}
						<li class="border-b border-line-subtle last:border-b-0">
							<a
								href={resolve(item.href)}
								class="group flex items-center gap-3 px-4 py-3 focus-ring transition-colors duration-fast hover:bg-surface-sunken"
							>
								<span
									class="flex size-9 shrink-0 items-center justify-center rounded-control bg-accent-soft text-accent"
								>
									<Icon name={item.icon} class="size-[18px]" />
								</span>
								<span class="min-w-0 flex-1">
									<span class="block text-sm font-medium text-fg">{item.title}</span>
									<span class="block truncate text-xs text-fg-muted">{item.description}</span>
								</span>
								<Icon
									name="chevron-right"
									class="size-4 text-fg-subtle transition-transform duration-fast group-hover:translate-x-0.5 rtl:rotate-180"
								/>
							</a>
						</li>
					{/each}
				</ul>
			</section>
		</div>
	</div>
{/if}
