<script>
	/**
	 * The public landing page. It speaks to both audiences NOVA serves — salons
	 * and spas that run their day on it, and customers who book through the
	 * marketplace — and sends each to their next step. Signed-in staff get a
	 * shortcut to /app; the dashboard itself lives only there.
	 */
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';

	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import Section from '$lib/components/marketing/Section.svelte';
	import SectionHeading from '$lib/components/marketing/SectionHeading.svelte';
	import BentoGrid from '$lib/components/marketing/BentoGrid.svelte';
	import BentoCard from '$lib/components/marketing/BentoCard.svelte';
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';

	/** @typedef {import('$lib/components/ui/Icon.svelte').IconName} IconName */

	/** @type {{ icon: IconName, title: string, body: string, span?: 1|2 }[]} */
	const features = [
		{
			icon: 'calendar',
			title: 'Bookings that never collide',
			body: 'Availability is calculated per provider, service and branch, and a slot is held the moment checkout starts.',
			span: 2
		},
		{
			icon: 'users',
			title: 'One line for walk-ins',
			body: 'Tickets, live positions and one-click call-next, side by side with appointments.'
		},
		{
			icon: 'chat-bubble',
			title: 'WhatsApp, built in',
			body: 'Confirmations, reminders and receipts arrive where customers already are.'
		},
		{
			icon: 'credit-card',
			title: 'Deposits that stop no-shows',
			body: 'Take a Mada or Apple Pay deposit through Moyasar before a booking is confirmed.'
		},
		{
			icon: 'globe',
			title: 'Arabic and English',
			body: 'Every service, branch and message is bilingual from the first record.'
		},
		{
			icon: 'chart-bar',
			title: 'Numbers you can act on',
			body: 'Revenue, utilization, retention and busiest hours — per branch, per provider.',
			span: 2
		}
	];

	/** @type {{ title: string, body: string }[]} */
	const steps = [
		{
			title: 'Set up your storefront',
			body: 'Add your branches, bilingual service menu and team. It takes minutes, not a project.'
		},
		{
			title: 'Open your calendar and queue',
			body: 'Customers book held slots online or join the walk-in line from their phone.'
		},
		{
			title: 'Run the day from one screen',
			body: 'Check in, start service, complete and get paid — with every customer kept in the loop.'
		}
	];

	/**
	 * A static sample of the day sheet, for the hero illustration only.
	 * @type {{ time: string, name: string, service: string, status: string, tone: 'success'|'info'|'accent'|'warning' }[]}
	 */
	const sampleDay = [
		{
			time: '10:00',
			name: 'Noura A.',
			service: 'Signature facial',
			status: 'Checked in',
			tone: 'info'
		},
		{ time: '10:30', name: 'Sara M.', service: 'Balayage', status: 'In service', tone: 'accent' },
		{
			time: '11:15',
			name: 'Reem K.',
			service: 'Hot stone massage',
			status: 'Confirmed',
			tone: 'success'
		},
		{
			time: '12:00',
			name: 'Huda S.',
			service: 'Classic manicure',
			status: 'Deposit due',
			tone: 'warning'
		}
	];

	/** @type {{ icon: IconName, label: string }[]} */
	const trust = [
		{ icon: 'credit-card', label: 'Payments by Moyasar' },
		{ icon: 'chat-bubble', label: 'WhatsApp messaging' },
		{ icon: 'shield-check', label: 'PDPL-aware consent' },
		{ icon: 'globe', label: 'Arabic & English' }
	];

	/** @type {{ eyebrow: string, icon: IconName, title: string, points: string[], cta: string, href: '/register'|'/discover' }[]} */
	const audiences = [
		{
			eyebrow: 'For salons & spas',
			icon: 'building',
			title: 'Run the whole day from one screen',
			points: [
				'Calendar, walk-in queue and day sheet together',
				'Deposits and payouts without spreadsheets',
				'Roles and permissions for every team member'
			],
			cta: 'Start free trial',
			href: '/register'
		},
		{
			eyebrow: 'For customers',
			icon: 'sparkles',
			title: 'Book a real slot in seconds',
			points: [
				'Live availability — no call-backs',
				'Confirmation and reminders on WhatsApp',
				'Pay a deposit with Mada or Apple Pay'
			],
			cta: 'Find a salon',
			href: '/discover'
		}
	];
</script>

<svelte:head>
	<title>NOVA — Bookings, queues and payments for GCC salons and spas</title>
</svelte:head>

<!-- Hero -->
<section class="relative isolate overflow-hidden">
	<GradientBlob variant="hero" />
	<Container
		size="xl"
		class="grid items-center gap-14 pt-16 pb-20 sm:pt-24 lg:grid-cols-[1.05fr_1fr] lg:pb-28"
	>
		<div class="animate-slide-up">
			<p
				class="inline-flex items-center gap-2 rounded-full border border-line bg-surface/80 px-3 py-1 text-xs font-medium text-fg-secondary backdrop-blur"
			>
				<span class="size-1.5 rounded-full bg-brand-500"></span>
				Built for salons and spas in the GCC
			</p>
			<h1 class="mt-6 text-display-2xl font-semibold tracking-tight text-fg">
				Everything your salon needs.
				<span
					class="text-transparent"
					style="background-image: var(--gradient-hero); -webkit-background-clip: text; background-clip: text;"
				>
					One operating system.
				</span>
			</h1>
			<p class="mt-6 max-w-xl text-body-lg text-fg-muted">
				Bookings, walk-ins, staff, payments and customer messages — synchronized in one place, in
				Arabic and English.
			</p>
			<div class="mt-9 flex flex-wrap gap-3">
				{#if authStore.isAuthenticated && authStore.isStaff}
					<Button size="lg" href={resolve('/app')}>
						Go to dashboard
						<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
					</Button>
				{:else}
					<Button size="lg" href={resolve('/register')}>
						Start free trial
						<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
					</Button>
				{/if}
				<Button size="lg" variant="outline" href={resolve('/discover')}>
					<Icon name="search" class="size-4" />
					Find a salon
				</Button>
			</div>
			<p class="mt-5 text-xs text-fg-muted">
				14-day free trial · No card required · Cancel anytime
			</p>
		</div>

		<!-- Illustrative product preview (static sample data) -->
		<div class="relative animate-slide-up [animation-delay:120ms]" aria-hidden="true">
			<div
				class="rounded-panel border border-line bg-surface/90 p-2 shadow-overlay backdrop-blur-xl"
			>
				<div
					class="rounded-[calc(var(--radius-panel)-0.5rem)] border border-line-subtle bg-surface"
				>
					<div class="flex items-center justify-between border-b border-line-subtle px-5 py-4">
						<div>
							<p class="text-xs text-fg-muted">Today · Olaya branch</p>
							<p class="font-semibold text-fg">Day sheet</p>
						</div>
						<div class="flex gap-4 text-end">
							<div>
								<p class="text-[11px] text-fg-muted">Booked</p>
								<p class="text-lg font-semibold text-fg tabular-nums">24</p>
							</div>
							<div>
								<p class="text-[11px] text-fg-muted">Waiting</p>
								<p class="text-lg font-semibold text-fg tabular-nums">3</p>
							</div>
						</div>
					</div>
					<ul class="divide-y divide-line-subtle">
						{#each sampleDay as row (row.time)}
							<li class="flex items-center gap-4 px-5 py-3">
								<span class="w-12 text-sm font-semibold text-accent tabular-nums">{row.time}</span>
								<div class="min-w-0 flex-1">
									<p class="truncate text-sm font-medium text-fg">{row.name}</p>
									<p class="truncate text-xs text-fg-muted">{row.service}</p>
								</div>
								<Badge tone={row.tone} size="sm" dot>{row.status}</Badge>
							</li>
						{/each}
					</ul>
				</div>
			</div>
			<div
				class="absolute -end-4 -top-6 hidden items-center gap-3 rounded-card border border-line bg-surface px-4 py-3 shadow-raised sm:flex"
			>
				<span
					class="flex size-9 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400"
				>
					<Icon name="chat-bubble" class="size-4" />
				</span>
				<div>
					<p class="text-xs font-semibold text-fg">Confirmation sent</p>
					<p class="text-[11px] text-fg-muted">WhatsApp · just now</p>
				</div>
			</div>
		</div>
	</Container>
</section>

<!-- Trust strip -->
<section class="border-y border-line bg-surface-sunken">
	<Container size="xl" class="flex flex-wrap items-center justify-center gap-x-10 gap-y-4 py-6">
		{#each trust as item (item.label)}
			<span class="inline-flex items-center gap-2 text-sm font-medium text-fg-muted">
				<Icon name={item.icon} class="size-4 text-fg-subtle" />
				{item.label}
			</span>
		{/each}
	</Container>
</section>

<!-- Two audiences -->
<Section>
	<Container size="xl">
		<SectionHeading
			align="center"
			eyebrow="One platform, two sides"
			title="Built for the business and the people it serves"
		/>
		<div class="mt-14 grid gap-5 lg:grid-cols-2">
			{#each audiences as side (side.eyebrow)}
				<div
					class="relative flex flex-col overflow-hidden rounded-panel border border-line bg-surface p-8 shadow-card sm:p-10"
				>
					<span
						class="flex size-11 items-center justify-center rounded-card bg-accent-soft text-accent"
					>
						<Icon name={side.icon} class="size-5" />
					</span>
					<p class="mt-6 text-xs font-semibold tracking-wider text-fg-muted uppercase">
						{side.eyebrow}
					</p>
					<h3 class="mt-2 text-display-md font-semibold tracking-tight text-fg">{side.title}</h3>
					<ul class="mt-6 flex flex-col gap-3">
						{#each side.points as point (point)}
							<li class="flex items-start gap-3 text-fg-secondary">
								<span
									class="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400"
								>
									<Icon name="check" class="size-3" />
								</span>
								{point}
							</li>
						{/each}
					</ul>
					<div class="mt-8 pt-2">
						<Button
							variant={side.href === '/register' ? 'primary' : 'outline'}
							href={resolve(side.href)}
						>
							{side.cta}
							<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
						</Button>
					</div>
				</div>
			{/each}
		</div>
	</Container>
</Section>

<!-- Features -->
<Section tone="sunken">
	<Container size="xl">
		<div class="flex flex-wrap items-end justify-between gap-6">
			<SectionHeading
				eyebrow="What's inside"
				title="The tools a front desk actually uses"
				subtitle="Each piece works on its own, and better together."
			/>
			<Button variant="ghost" href={resolve('/features')}>
				All features
				<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
			</Button>
		</div>
		<BentoGrid class="mt-12">
			{#each features as feature (feature.title)}
				<BentoCard span={feature.span ?? 1}>
					<span
						class="flex size-10 items-center justify-center rounded-control bg-accent-soft text-accent"
					>
						<Icon name={feature.icon} class="size-5" />
					</span>
					<h3 class="mt-5 font-semibold text-fg">{feature.title}</h3>
					<p class="mt-2 text-sm text-fg-muted">{feature.body}</p>
				</BentoCard>
			{/each}
		</BentoGrid>
	</Container>
</Section>

<!-- How it works -->
<Section>
	<Container size="xl">
		<SectionHeading align="center" eyebrow="How it works" title="Live in an afternoon" />
		<ol class="mt-14 grid gap-8 md:grid-cols-3">
			{#each steps as item, index (item.title)}
				<li class="relative">
					<span
						class="flex size-10 items-center justify-center rounded-full border border-line bg-surface text-sm font-semibold text-accent tabular-nums shadow-card"
					>
						{index + 1}
					</span>
					{#if index < steps.length - 1}
						<span
							class="absolute start-14 top-5 hidden h-px w-[calc(100%-3.5rem)] bg-line md:block"
							aria-hidden="true"
						></span>
					{/if}
					<h3 class="mt-5 font-semibold text-fg">{item.title}</h3>
					<p class="mt-2 text-sm text-fg-muted">{item.body}</p>
				</li>
			{/each}
		</ol>
	</Container>
</Section>

<!-- CTA -->
<Section
	tone="dark"
	padding="tight"
	class="mx-4 mb-16 rounded-panel sm:mx-6 lg:mx-auto lg:max-w-7xl"
>
	<GradientBlob variant="corner" />
	<Container size="lg" class="relative py-8 text-center sm:py-12">
		<h2 class="text-display-lg font-semibold tracking-tight text-white">
			Your next customer is already looking.
		</h2>
		<p class="mx-auto mt-4 max-w-xl text-body-lg text-white/80">
			Give them a faster way to find you, book and stay connected.
		</p>
		<div class="mt-8 flex flex-wrap justify-center gap-3">
			<Button size="lg" variant="inverse" href={resolve('/register')}>Start free trial</Button>
			<Button size="lg" variant="outline-inverse" href={resolve('/pricing')}>See pricing</Button>
		</div>
	</Container>
</Section>
