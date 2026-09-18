<script>
	import { resolve } from '$app/paths';
	import { businessStore } from '$lib/stores/business.svelte.js';
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { listBookings } from '$lib/api/booking.js';
	import { listServices, listProviders, listLocations } from '$lib/api/catalog.js';
	import { formatMoney } from '$lib/utils/money.js';

	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';

	let businessId = $derived(businessStore.activeBusinessId);
	let tenantId = $derived(tenantStore.activeTenantId);

	let loading = $state(true);
	let bookingCount = $state(0);
	let confirmedCount = $state(0);
	let serviceCount = $state(0);
	let providerCount = $state(0);
	let locationCount = $state(0);
	let recentBookings = $state([]);

	const modules = [
		{
			title: 'Queue',
			label: 'Front desk',
			description: 'Walk-ins, tickets and live customer flow.',
			icon: 'users',
			href: '/app/queue',
			tone: 'accent'
		},
		{
			title: 'Bookings',
			label: 'Schedule',
			description: 'Manage today’s appointments and visits.',
			icon: 'calendar',
			href: '/app/bookings',
			tone: 'success'
		},
		{
			title: 'Catalog',
			label: 'Services',
			description: 'Services, pricing, branches and providers.',
			icon: 'sparkles',
			href: '/app/catalog',
			tone: 'neutral'
		},
		{
			title: 'Billing',
			label: 'Finance',
			description: 'Payments, deposits and settlements.',
			icon: 'credit-card',
			href: '/app/billing',
			tone: 'success'
		},
		{
			title: 'Team',
			label: 'Access',
			description: 'Staff roles and permissions.',
			icon: 'user-check',
			href: '/app/team',
			tone: 'neutral'
		},
		{
			title: 'Analytics',
			label: 'Insights',
			description: 'Performance, retention and revenue.',
			icon: 'chart-bar',
			href: '/app/analytics',
			tone: 'info'
		}
	];

	$effect(() => {
		if (!tenantId || !businessId) {
			loading = false;
			return;
		}

		let cancelled = false;

		async function loadDashboard() {
			loading = true;

			try {
				const [bookingsRes, locationsRes] = await Promise.all([
					listBookings(tenantId, { limit: 10 }).catch(() => ({ items: [] })),
					listLocations(tenantId, businessId).catch(() => ({ items: [] }))
				]);

				if (cancelled) return;

				const bookings = bookingsRes?.items ?? [];
				const locations = locationsRes?.items ?? [];

				recentBookings = bookings.slice(0, 5);
				bookingCount = bookings.length;
				confirmedCount = bookings.filter(
					(booking) =>
						booking.status === 'confirmed' ||
						booking.status === 'in_service'
				).length;

				locationCount = locations.length;

				const [services, providers] = await Promise.all([
					Promise.all(
						locations.map((location) =>
							listServices(tenantId, location.id).catch(() => ({ items: [] }))
						)
					),
					Promise.all(
						locations.map((location) =>
							listProviders(tenantId, location.id).catch(() => ({ items: [] }))
						)
					)
				]);

				if (cancelled) return;

				serviceCount = services.reduce(
					(total, response) => total + (response?.items?.length ?? 0),
					0
				);

				providerCount = providers.reduce(
					(total, response) => total + (response?.items?.length ?? 0),
					0
				);
			} finally {
				if (!cancelled) loading = false;
			}
		}

		loadDashboard();

		return () => {
			cancelled = true;
		};
	});
</script>

<svelte:head>
	<title>Command Center — NOVA</title>
</svelte:head>

<div class="min-h-full space-y-10 max-w-7xl mx-auto">

	<!-- ========================================================= -->
	<!-- HERO -->
	<!-- ========================================================= -->

	<section
		class="relative overflow-hidden rounded-[2rem] border border-slate-200 bg-slate-950 text-white shadow-xl dark:border-slate-800 mt-10"
	>
		<!-- Ambient light -->
		<div
			class="pointer-events-none absolute -right-32 -top-32 size-96 rounded-full bg-brand-500/20 blur-3xl"
		></div>

		<div
			class="pointer-events-none absolute -bottom-40 left-1/3 size-96 rounded-full bg-blue-500/10 blur-3xl"
		></div>

		<div class="relative grid lg:grid-cols-[1.4fr_0.6fr]">

			<!-- Main hero copy -->
			<div class="flex flex-col justify-between p-7 sm:p-10 lg:p-14">

				<div>
					<div class="mb-6 flex items-center gap-3">
						<span class="flex size-2.5 rounded-full bg-emerald-400 animate-pulse"></span>

						<span class="text-[11px] font-bold uppercase tracking-[0.2em] text-emerald-300">
							Live Command Center
						</span>

						<span class="text-slate-600">/</span>

						<span class="text-[11px] uppercase tracking-wider text-slate-400">
							NOVA OS
						</span>
					</div>

					<h1
						class="max-w-3xl text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl"
					>
						Everything your salon needs.
						<span class="text-slate-400">
							One operating system.
						</span>
					</h1>

					<p
						class="mt-6 max-w-2xl text-sm leading-7 text-slate-400 sm:text-base"
					>
						Run bookings, walk-ins, staff, services, payments and customer
						relationships from one synchronized command center.
					</p>
				</div>

				<div class="mt-10 flex flex-wrap gap-3">
					<Button href={resolve('/app/queue')} size="md">
						<Icon name="users" class="size-4" />
						Open live queue
					</Button>

					<Button
						href={resolve('/app/bookings')}
						variant="outline"
						size="md"
						class="border-slate-700 bg-white/5 text-white hover:bg-white/10"
					>
						<Icon name="calendar" class="size-4" />
						View day sheet
					</Button>
				</div>
			</div>

			<!-- Hero telemetry -->
			<div class="border-t border-white/10 bg-white/[0.03] lg:border-l lg:border-t-0">

				<div class="grid h-full grid-cols-2">

					<div class="border-b border-r border-white/10 p-6">
						<span class="text-[10px] font-bold uppercase tracking-widest text-slate-500">
							Appointments
						</span>

						<p class="mt-3 font-mono text-4xl font-bold">
							{loading ? '—' : bookingCount}
						</p>

						<p class="mt-2 text-xs text-emerald-400">
							{confirmedCount} active
						</p>
					</div>

					<div class="border-b border-white/10 p-6">
						<span class="text-[10px] font-bold uppercase tracking-widest text-slate-500">
							Providers
						</span>

						<p class="mt-3 font-mono text-4xl font-bold">
							{loading ? '—' : providerCount}
						</p>

						<p class="mt-2 text-xs text-slate-500">
							Across {locationCount || 1} locations
						</p>
					</div>

					<div class="border-r border-white/10 p-6">
						<span class="text-[10px] font-bold uppercase tracking-widest text-slate-500">
							Services
						</span>

						<p class="mt-3 font-mono text-4xl font-bold">
							{loading ? '—' : serviceCount}
						</p>

						<p class="mt-2 text-xs text-slate-500">
							Arabic + English
						</p>
					</div>

					<div class="p-6">
						<span class="text-[10px] font-bold uppercase tracking-widest text-slate-500">
							Protection
						</span>

						<p class="mt-3 font-mono text-4xl font-bold text-emerald-400">
							86%
						</p>

						<p class="mt-2 text-xs text-slate-500">
							No-show shield
						</p>
					</div>

				</div>
			</div>
		</div>
	</section>


	<!-- ========================================================= -->
	<!-- SYSTEM STATUS -->
	<!-- ========================================================= -->

	<section class="flex flex-wrap items-center justify-between gap-4">

		<div>
			<p class="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">
				System status
			</p>

			<h2 class="mt-1 text-lg font-bold text-slate-900 dark:text-white">
				Your operation is synchronized
			</h2>
		</div>

		<div class="flex flex-wrap gap-2">
			<Badge tone="success" size="sm">Moyasar connected</Badge>
			<Badge tone="neutral" size="sm">ZATCA Phase 2</Badge>
			<Badge tone="accent" size="sm">Live sync</Badge>
		</div>

	</section>


	<!-- ========================================================= -->
	<!-- MODULE NAVIGATION -->
	<!-- ========================================================= -->

	<section>

		<div class="mb-5 flex items-end justify-between gap-4">
			<div>
				<p class="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">
					Workspace
				</p>

				<h2 class="mt-1 text-xl font-bold text-slate-900 dark:text-white">
					Operating modules
				</h2>
			</div>

			<span class="hidden text-xs text-slate-400 sm:block">
				Everything connected. Everything in one place.
			</span>
		</div>


		<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">

			{#each modules as module (module.href)}

				<a
					href={resolve(module.href)}
					class="group relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 transition-all duration-300 hover:-translate-y-1 hover:border-brand-300 hover:shadow-lg dark:border-slate-800 dark:bg-slate-900 dark:hover:border-brand-800"
				>

					<div class="flex items-start justify-between">

						<div
							class="flex size-11 items-center justify-center rounded-xl bg-slate-100 text-slate-700 transition-colors group-hover:bg-brand-50 group-hover:text-brand-600 dark:bg-slate-800 dark:text-slate-300 dark:group-hover:bg-brand-950/40 dark:group-hover:text-brand-400"
						>
							<Icon name={module.icon} class="size-5" />
						</div>

						<Icon
							name="arrow-right"
							class="size-4 text-slate-300 transition-all group-hover:translate-x-1 group-hover:text-brand-500"
						/>

					</div>

					<p
						class="mt-6 text-[10px] font-bold uppercase tracking-widest text-slate-400"
					>
						{module.label}
					</p>

					<h3
						class="mt-1 text-lg font-bold text-slate-900 dark:text-white"
					>
						{module.title}
					</h3>

					<p class="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">
						{module.description}
					</p>

				</a>

			{/each}

		</div>
	</section>


	<!-- ========================================================= -->
	<!-- LIVE OPERATIONS -->
	<!-- ========================================================= -->

	<section class="grid gap-6 lg:grid-cols-[1fr_320px]">

		<!-- Activity stream -->
		<Card padding="none">

			<div class="flex items-center justify-between border-b border-slate-100 p-6 dark:border-slate-800">

				<div>
					<p class="text-[10px] font-bold uppercase tracking-widest text-slate-400">
						Live operations
					</p>

					<h2 class="mt-1 text-base font-bold text-slate-900 dark:text-white">
						Today’s activity
					</h2>
				</div>

				<Button
					href={resolve('/app/bookings')}
					variant="outline"
					size="sm"
				>
					Day sheet
				</Button>

			</div>

			{#if recentBookings.length > 0}

				<div class="divide-y divide-slate-100 dark:divide-slate-800">

					{#each recentBookings as booking (booking.id)}

						<div class="flex items-center justify-between gap-4 p-5">

							<div class="flex min-w-0 items-center gap-4">

								<div
									class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 font-mono text-xs font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300"
								>
									{booking.starts_at
										? new Date(booking.starts_at).toLocaleTimeString('en-US', {
												hour: '2-digit',
												minute: '2-digit'
											})
										: '—'}
								</div>

								<div class="min-w-0">
									<p class="truncate text-sm font-semibold text-slate-900 dark:text-white">
										{booking.customer_name || 'Walk-in Guest'}
									</p>

									<p class="truncate text-xs text-slate-500">
										{booking.service_name || 'Salon Service'}
									</p>
								</div>

							</div>

							<div class="flex shrink-0 items-center gap-3">

								<span class="hidden font-mono text-xs font-semibold text-emerald-600 sm:block">
									{booking.price
										? formatMoney(booking.price, booking.currency, 'en')
										: 'Deposit paid'}
								</span>

								<Badge
									tone={booking.status === 'confirmed' ? 'success' : 'neutral'}
									size="sm"
								>
									{booking.status}
								</Badge>

							</div>

						</div>

					{/each}

				</div>

			{:else}

				<div class="p-10 text-center">
					<Icon name="calendar" class="mx-auto size-8 text-slate-300" />

					<p class="mt-3 text-sm font-medium text-slate-700 dark:text-slate-300">
						No recent bookings
					</p>

					<p class="mt-1 text-xs text-slate-400">
						New appointments will appear here.
					</p>
				</div>

			{/if}

		</Card>


		<!-- Quick control panel -->
		<Card padding="lg">

			<p class="text-[10px] font-bold uppercase tracking-widest text-slate-400">
				Quick controls
			</p>

			<h2 class="mt-1 text-base font-bold text-slate-900 dark:text-white">
				Go directly to work
			</h2>

			<div class="mt-5 space-y-2">

				<a
					href={resolve('/app/queue')}
					class="flex items-center gap-3 rounded-xl border border-slate-200 p-3 text-sm font-medium text-slate-700 transition hover:border-brand-300 hover:text-brand-600 dark:border-slate-800 dark:text-slate-300"
				>
					<Icon name="users" class="size-4" />
					Open queue
				</a>

				<a
					href={resolve('/app/bookings')}
					class="flex items-center gap-3 rounded-xl border border-slate-200 p-3 text-sm font-medium text-slate-700 transition hover:border-brand-300 hover:text-brand-600 dark:border-slate-800 dark:text-slate-300"
				>
					<Icon name="calendar" class="size-4" />
					Today's bookings
				</a>

				<a
					href={resolve('/app/catalog')}
					class="flex items-center gap-3 rounded-xl border border-slate-200 p-3 text-sm font-medium text-slate-700 transition hover:border-brand-300 hover:text-brand-600 dark:border-slate-800 dark:text-slate-300"
				>
					<Icon name="sparkles" class="size-4" />
					Service catalog
				</a>

				<a
					href={resolve('/app/billing')}
					class="flex items-center gap-3 rounded-xl border border-slate-200 p-3 text-sm font-medium text-slate-700 transition hover:border-brand-300 hover:text-brand-600 dark:border-slate-800 dark:text-slate-300"
				>
					<Icon name="credit-card" class="size-4" />
					Billing
				</a>

			</div>

		</Card>

	</section>


	<!-- ========================================================= -->
	<!-- ONBOARDING -->
	<!-- ========================================================= -->

	{#if !businessId}

		<section
			class="overflow-hidden rounded-2xl border border-brand-200 bg-brand-50/60 dark:border-brand-900/60 dark:bg-brand-950/30"
		>

			<div class="flex flex-col gap-6 p-6 sm:flex-row sm:items-center sm:justify-between">

				<div class="flex items-start gap-4">

					<div
						class="flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white"
					>
						<Icon name="sparkles" class="size-5" />
					</div>

					<div>
						<h2 class="font-bold text-slate-900 dark:text-white">
							Complete your storefront
						</h2>

						<p class="mt-1 max-w-xl text-sm leading-6 text-slate-600 dark:text-slate-400">
							Set up your primary location, services and staff before
							accepting online bookings.
						</p>
					</div>

				</div>

				<Button href={resolve('/app/catalog')} size="sm">
					Complete setup
				</Button>

			</div>

		</section>

	{/if}

</div>
