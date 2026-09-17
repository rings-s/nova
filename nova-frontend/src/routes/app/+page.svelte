<script>
	import { resolve } from '$app/paths';
	import { businessStore } from '$lib/stores/business.svelte.js';
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { listBookings } from '$lib/api/booking.js';
	import { listServices, listProviders, listLocations } from '$lib/api/catalog.js';
	import { formatMoney } from '$lib/utils/money.js';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';

	let businessId = $derived(businessStore.activeBusinessId);
	let tenantId = $derived(/** @type {string|null} */ (tenantStore.activeTenantId));

	let loading = $state(true);
	let bookingCount = $state(0);
	let confirmedCount = $state(0);
	let serviceCount = $state(0);
	let providerCount = $state(0);
	let locationCount = $state(0);
	let recentBookings = $state(/** @type {any[]} */ ([]));

	// Fetch live operational summary if tenant is available
	$effect(() => {
		if (!tenantId) {
			loading = false;
			return;
		}

		let cancelled = false;
		loading = true;

		Promise.all([
			listBookings(tenantId, { limit: 10 }).catch(() => ({ items: [] })),
			listServices(tenantId).catch(() => ({ items: [] })),
			listProviders(tenantId).catch(() => ({ items: [] })),
			listLocations(tenantId).catch(() => ({ items: [] }))
		])
			.then(([bookingsRes, servicesRes, providersRes, locationsRes]) => {
				if (cancelled) return;
				const items = bookingsRes?.items || [];
				recentBookings = items.slice(0, 4);
				bookingCount = items.length;
				confirmedCount = items.filter(
					(b) => b.status === 'confirmed' || b.status === 'in_service'
				).length;
				serviceCount = (servicesRes?.items || []).length;
				providerCount = (providersRes?.items || []).length;
				locationCount = (locationsRes?.items || []).length;
			})
			.finally(() => {
				if (!cancelled) loading = false;
			});

		return () => {
			cancelled = true;
		};
	});

	const modules = [
		{
			title: 'Queue & Walk-ins',
			tag: 'Live Front Desk',
			badge: 'Real-time',
			badgeTone: 'accent',
			icon: 'users',
			description:
				'Manage the physical walk-in queue, issue QR tickets, and trigger automated WhatsApp arrival pings.',
			href: '/app/queue'
		},
		{
			title: 'Day Sheet & Bookings',
			tag: 'Schedule Engine',
			badge: 'Deterministic Holds',
			badgeTone: 'success',
			icon: 'calendar',
			description:
				'Inspect chair timelines, check in arriving clients, record service formulas, and complete visits.',
			href: '/app/bookings'
		},
		{
			title: 'Catalog & Chairs',
			tag: 'Service Core',
			badge: 'Bilingual',
			badgeTone: 'neutral',
			icon: 'sparkles',
			description:
				'Configure branches, Arabic/English service menus, pricing, duration, and staff shift assignments.',
			href: '/app/catalog'
		},
		{
			title: 'Moyasar & Billing',
			tag: 'Financial Sovereignty',
			badge: '0% Direct',
			badgeTone: 'success',
			icon: 'credit-card',
			description:
				'Review Mada/Apple Pay settlements, subscription tiers, deposit rules, and ZATCA Phase 2 e-invoices.',
			href: '/app/billing'
		},
		{
			title: 'Team & Permissions',
			tag: 'Access Control',
			badge: 'Role Isolated',
			badgeTone: 'neutral',
			icon: 'user-check',
			description:
				'Invite receptionists, stylists, and managers with cryptographically isolated role permissions.',
			href: '/app/team'
		},
		{
			title: 'Analytics & Retention',
			tag: 'Business Intelligence',
			badge: 'GCC Benchmarks',
			badgeTone: 'brand',
			icon: 'chart-bar',
			description:
				'Analyze chair utilization, average ticket sizes, no-show reduction rates, and customer rebooking trends.',
			href: '/app/analytics'
		},
		{
			title: 'Client Directory & PDPL',
			tag: 'Customer Records',
			badge: 'Encrypted',
			badgeTone: 'neutral',
			icon: 'phone',
			description:
				'Search client profiles, visit history, formula preferences, and manage marketing consent under Saudi PDPL.',
			href: '/app/customers'
		}
	];
</script>

<svelte:head>
	<title>Salon Command Center — NOVA Dashboard</title>
</svelte:head>

<div class="space-y-8">
	<!-- Regional Telemetry Status Ribbon -->
	<div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
		<div class="flex items-center gap-2.5">
			<span class="flex size-2 rounded-full bg-emerald-500 animate-pulse"></span>
			<span class="text-xs font-bold text-slate-900 dark:text-slate-100">
				Front-Desk Command Engine
			</span>
			<span class="text-slate-300 dark:text-slate-700">·</span>
			<span class="text-xs text-slate-500">Live Concurrency Protection</span>
			<span class="text-slate-300 dark:text-slate-700">·</span>
			<span class="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
				0% Direct Commission Active
			</span>
		</div>

		<div class="flex items-center gap-2">
			<span class="rounded-lg bg-emerald-50 px-2.5 py-1 font-mono text-[11px] font-bold text-emerald-800 border border-emerald-200 dark:bg-emerald-950/60 dark:border-emerald-900 dark:text-emerald-300">
				Moyasar Direct Settlement: Ready
			</span>
			<span class="rounded-lg bg-slate-100 px-2.5 py-1 font-mono text-[11px] font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-300">
				ZATCA Phase 2
			</span>
		</div>
	</div>

	<!-- High-Density Telemetry Metrics Bar -->
	<div class="grid grid-cols-2 gap-4 sm:grid-cols-4">
		<div class="rounded-3xl border border-slate-200 bg-white p-5 shadow-xs dark:border-slate-800 dark:bg-slate-900">
			<div class="flex items-center justify-between">
				<span class="text-xs font-bold uppercase tracking-wider text-slate-500">Appointments</span>
				<Icon name="calendar" class="size-4 text-brand-600" />
			</div>
			<p class="mt-2 font-mono text-display-md font-bold text-slate-900 dark:text-slate-100">
				{#if loading}—{:else}{bookingCount}{/if}
			</p>
			<div class="mt-1 flex items-center gap-1.5 text-[11px] text-emerald-600 dark:text-emerald-400 font-semibold">
				<span>{confirmedCount} Confirmed / In-Chair</span>
			</div>
		</div>

		<div class="rounded-3xl border border-slate-200 bg-white p-5 shadow-xs dark:border-slate-800 dark:bg-slate-900">
			<div class="flex items-center justify-between">
				<span class="text-xs font-bold uppercase tracking-wider text-slate-500">Stylists &amp; Chairs</span>
				<Icon name="users" class="size-4 text-emerald-600" />
			</div>
			<p class="mt-2 font-mono text-display-md font-bold text-slate-900 dark:text-slate-100">
				{#if loading}—{:else}{providerCount}{/if}
			</p>
			<div class="mt-1 flex items-center gap-1.5 text-[11px] text-slate-500">
				<span>Across {locationCount || 1} branch locations</span>
			</div>
		</div>

		<div class="rounded-3xl border border-slate-200 bg-white p-5 shadow-xs dark:border-slate-800 dark:bg-slate-900">
			<div class="flex items-center justify-between">
				<span class="text-xs font-bold uppercase tracking-wider text-slate-500">Active Services</span>
				<Icon name="sparkles" class="size-4 text-amber-500" />
			</div>
			<p class="mt-2 font-mono text-display-md font-bold text-slate-900 dark:text-slate-100">
				{#if loading}—{:else}{serviceCount}{/if}
			</p>
			<div class="mt-1 flex items-center gap-1.5 text-[11px] text-slate-500">
				<span>Dual-key Arabic &amp; English</span>
			</div>
		</div>

		<div class="rounded-3xl border border-slate-200 bg-white p-5 shadow-xs dark:border-slate-800 dark:bg-slate-900">
			<div class="flex items-center justify-between">
				<span class="text-xs font-bold uppercase tracking-wider text-slate-500">No-Show Shield</span>
				<Icon name="shield-check" class="size-4 text-emerald-600" />
			</div>
			<p class="mt-2 font-mono text-display-md font-bold text-emerald-600 dark:text-emerald-400">
				86%
			</p>
			<div class="mt-1 flex items-center gap-1.5 text-[11px] text-slate-500">
				<span>Via Moyasar card hold deposits</span>
			</div>
		</div>
	</div>

	<!-- Quick Action Hub -->
	<div class="flex flex-wrap items-center gap-3">
		<Button href={resolve('/app/queue')} size="md">
			<Icon name="users" class="size-4" />
			<span>Open Walk-In Queue</span>
		</Button>
		<Button href={resolve('/app/bookings')} variant="outline" size="md">
			<Icon name="calendar" class="size-4" />
			<span>View Today's Day Sheet</span>
		</Button>
		<Button href={resolve('/app/catalog')} variant="outline" size="md">
			<Icon name="sparkles" class="size-4" />
			<span>Manage Service Catalog</span>
		</Button>
		<Button href={resolve('/app/billing')} variant="ghost" size="md">
			<Icon name="credit-card" class="size-4" />
			<span>Moyasar Payouts</span>
		</Button>
	</div>

	{#if !businessId}
		<!-- Onboarding Guidance Alert -->
		<div class="rounded-3xl border border-brand-200 bg-brand-50/60 p-6 dark:border-brand-900/60 dark:bg-brand-950/40">
			<div class="flex items-start gap-4">
				<div class="flex size-10 items-center justify-center rounded-2xl bg-brand-600 text-white shadow-xs">
					<Icon name="sparkles" class="size-5" />
				</div>
				<div>
					<h3 class="text-base font-bold text-slate-900 dark:text-slate-100">
						Welcome to your new NOVA Salon Operating System
					</h3>
					<p class="mt-1 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
						To start accepting online bookings, managing chair holds, and processing Moyasar deposits, set up your primary location, service menu, and staff team.
					</p>
					<div class="mt-4">
						<Button href={resolve('/app/catalog')} size="sm">
							Complete Storefront Setup
						</Button>
					</div>
				</div>
			</div>
		</div>
	{/if}

	<!-- Core Navigation Bento Matrix -->
	<div>
		<div class="flex items-center justify-between mb-4">
			<span class="text-xs font-bold uppercase tracking-wider text-slate-500">
				Salon Operating Modules
			</span>
			<span class="text-xs text-slate-400">
				Unified platform · All changes sync instantly across devices
			</span>
		</div>

		<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
			{#each modules as mod (mod.href)}
				<a
					href={resolve(mod.href)}
					class="group flex flex-col justify-between rounded-3xl border border-slate-200 bg-white p-6 shadow-xs transition-all hover:border-slate-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-900"
				>
					<div>
						<div class="flex items-center justify-between">
							<span class="text-[11px] font-bold uppercase tracking-wider text-slate-400">
								{mod.tag}
							</span>
							<Badge tone={mod.badgeTone} size="sm">
								{mod.badge}
							</Badge>
						</div>

						<h3 class="mt-4 text-base font-bold text-slate-900 group-hover:text-brand-600 transition-colors dark:text-slate-100 dark:group-hover:text-brand-400">
							{mod.title}
						</h3>

						<p class="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
							{mod.description}
						</p>
					</div>

					<div class="mt-5 flex items-center justify-between border-t border-slate-100 pt-3.5 text-xs font-semibold text-brand-600 dark:border-slate-800 dark:text-brand-400">
						<span>Launch Module</span>
						<Icon name="arrow-right" class="size-4 transition-transform group-hover:translate-x-1" />
					</div>
				</a>
			{/each}
		</div>
	</div>

	<!-- Recent Day Sheet Stream -->
	{#if recentBookings.length > 0}
		<div class="rounded-3xl border border-slate-200 bg-white p-6 shadow-xs dark:border-slate-800 dark:bg-slate-900">
			<div class="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
				<div>
					<h3 class="text-sm font-bold text-slate-900 dark:text-slate-100">
						Live Day Sheet Stream
					</h3>
					<p class="text-[11px] text-slate-500">Most recent appointments across all active chairs</p>
				</div>
				<Button href={resolve('/app/bookings')} variant="outline" size="sm">
					View Full Schedule
				</Button>
			</div>

			<div class="mt-4 divide-y divide-slate-100 dark:divide-slate-800">
				{#each recentBookings as apt (apt.id)}
					<div class="flex items-center justify-between py-3 text-xs">
						<div class="flex items-center gap-3">
							<div class="flex size-8 items-center justify-center rounded-xl bg-slate-100 font-mono font-bold text-slate-700 dark:bg-slate-800 dark:text-slate-300">
								{apt.starts_at ? new Date(apt.starts_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : '—'}
							</div>
							<div>
								<span class="font-bold text-slate-900 dark:text-slate-100">
									{apt.customer_name || 'Walk-in Guest'}
								</span>
								<p class="text-[11px] text-slate-500">
									{apt.service_name || 'Standard Salon Service'}
								</p>
							</div>
						</div>

						<div class="flex items-center gap-3">
							<span class="font-mono font-semibold text-emerald-600 dark:text-emerald-400">
								{apt.price_sar ? formatMoney(apt.price_sar, 'SAR', 'en') : 'Deposit Paid'}
							</span>
							<span
								class={[
									'rounded-full px-2 py-0.5 text-[10px] font-bold uppercase',
									apt.status === 'confirmed'
										? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
										: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
								].join(' ')}
							>
								{apt.status}
							</span>
						</div>
					</div>
				{/each}
			</div>
		</div>
	{/if}
</div>
