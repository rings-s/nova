<script>
	import { t, m } from '$lib/i18n/index.svelte.js';
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
			title: m('Bookings that never collide'),
			body: m(
				'Availability is calculated per provider, service and branch, and a slot is held the moment checkout starts.'
			),
			span: 2
		},
		{
			icon: 'users',
			title: m('One line for walk-ins'),
			body: m('Tickets, live positions and one-click call-next, side by side with appointments.')
		},
		{
			icon: 'chat-bubble',
			title: m('WhatsApp, built in'),
			body: m('Confirmations, reminders and receipts arrive where customers already are.')
		},
		{
			icon: 'credit-card',
			title: m('Deposits that stop no-shows'),
			body: m('Take a Mada or Apple Pay deposit through Moyasar before a booking is confirmed.')
		},
		{
			icon: 'globe',
			title: m('Arabic and English'),
			body: m('Every service, branch and message is bilingual from the first record.')
		},
		{
			icon: 'chart-bar',
			title: m('Numbers you can act on'),
			body: m('Revenue, utilization, retention and busiest hours — per branch, per provider.'),
			span: 2
		}
	];

	/** @type {{ title: string, body: string }[]} */
	const steps = [
		{
			title: m('Set up your storefront'),
			body: m(
				'Add your branches, bilingual service menu and team. It takes minutes, not a project.'
			)
		},
		{
			title: m('Open your calendar and queue'),
			body: m('Customers book held slots online or join the walk-in line from their phone.')
		},
		{
			title: m('Run the day from one screen'),
			body: m(
				'Check in, start service, complete and get paid — with every customer kept in the loop.'
			)
		}
	];

	/**
	 * A static sample of the day sheet, for the hero illustration only.
	 * @type {{ time: string, name: string, service: string, status: string, tone: 'success'|'info'|'accent'|'warning' }[]}
	 */
	const sampleDay = [
		{
			time: '10:00',
			name: m('Noura A.'),
			service: m('Signature facial'),
			status: m('Checked in'),
			tone: 'info'
		},
		{
			time: '10:30',
			name: m('Sara M.'),
			service: m('Balayage'),
			status: m('In service'),
			tone: 'accent'
		},
		{
			time: '11:15',
			name: m('Reem K.'),
			service: m('Hot stone massage'),
			status: m('Confirmed'),
			tone: 'success'
		},
		{
			time: '12:00',
			name: m('Huda S.'),
			service: m('Classic manicure'),
			status: m('Deposit due'),
			tone: 'warning'
		}
	];

	/** @type {{ icon: IconName, label: string }[]} */
	const trust = [
		{ icon: 'credit-card', label: m('Payments by Moyasar') },
		{ icon: 'chat-bubble', label: m('WhatsApp messaging') },
		{ icon: 'shield-check', label: m('PDPL-aware consent') },
		{ icon: 'globe', label: m('Arabic & English') }
	];

	/** @type {{ eyebrow: string, icon: IconName, title: string, points: string[], cta: string, href: '/register'|'/discover' }[]} */
	const audiences = [
		{
			eyebrow: m('For salons & spas'),
			icon: 'building',
			title: m('Run the whole day from one screen'),
			points: [
				m('Calendar, walk-in queue and day sheet together'),
				m('Deposits and payouts without spreadsheets'),
				m('Roles and permissions for every team member')
			],
			cta: m('Start free trial'),
			href: '/register'
		},
		{
			eyebrow: m('For customers'),
			icon: 'sparkles',
			title: m('Book a real slot in seconds'),
			points: [
				m('Live availability — no call-backs'),
				m('Confirmation and reminders on WhatsApp'),
				m('Pay a deposit with Mada or Apple Pay')
			],
			cta: m('Find a salon'),
			href: '/discover'
		}
	];
</script>

<svelte:head>
	<title>{t('NOVA — Bookings, queues and payments for GCC salons and spas')}</title>
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
				{t('Built for salons and spas in the GCC')}
			</p>
			<h1 class="mt-6 text-display-2xl font-semibold tracking-tight text-fg">
				{t('Everything your salon needs.')}
				<span
					class="text-transparent"
					style="background-image: var(--gradient-hero); -webkit-background-clip: text; background-clip: text;"
				>
					{t('One operating system.')}
				</span>
			</h1>
			<p class="mt-6 max-w-xl text-body-lg text-fg-muted">
				{t(
					'Bookings, walk-ins, staff, payments and customer messages — synchronized in one place, in Arabic and English.'
				)}
			</p>
			<div class="mt-9 flex flex-wrap gap-3">
				{#if authStore.isAuthenticated && authStore.isStaff}
					<Button size="lg" href={resolve('/app')}>
						{t('Go to dashboard')}
						<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
					</Button>
				{:else}
					<Button size="lg" href={`${resolve('/register')}?as=business`}>
						{t('Start free trial')}
						<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
					</Button>
				{/if}
				<Button size="lg" variant="outline" href={resolve('/discover')}>
					<Icon name="search" class="size-4" />
					{t('Find a salon')}
				</Button>
			</div>
			<p class="mt-5 text-xs text-fg-muted">
				{t('14-day free trial · No card required · Cancel anytime')}
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
							<p class="text-xs text-fg-muted">{t('Today · Olaya branch')}</p>
							<p class="font-semibold text-fg">{t('Day sheet')}</p>
						</div>
						<div class="flex gap-4 text-end">
							<div>
								<p class="text-[11px] text-fg-muted">{t('Booked')}</p>
								<p class="text-lg font-semibold text-fg tabular-nums">24</p>
							</div>
							<div>
								<p class="text-[11px] text-fg-muted">{t('Waiting')}</p>
								<p class="text-lg font-semibold text-fg tabular-nums">3</p>
							</div>
						</div>
					</div>
					<ul class="divide-y divide-line-subtle">
						{#each sampleDay as row (row.time)}
							<li class="flex items-center gap-4 px-5 py-3">
								<span class="w-12 text-sm font-semibold text-accent tabular-nums">{row.time}</span>
								<div class="min-w-0 flex-1">
									<p class="truncate text-sm font-medium text-fg">{t(row.name)}</p>
									<p class="truncate text-xs text-fg-muted">{t(row.service)}</p>
								</div>
								<Badge tone={row.tone} size="sm" dot>{t(row.status)}</Badge>
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
					<p class="text-xs font-semibold text-fg">{t('Confirmation sent')}</p>
					<p class="text-[11px] text-fg-muted">{t('WhatsApp · just now')}</p>
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
				{t(item.label)}
			</span>
		{/each}
	</Container>
</section>

<!-- Two audiences -->
<Section>
	<Container size="xl">
		<SectionHeading
			align="center"
			eyebrow={t('One platform, two sides')}
			title={t('Built for the business and the people it serves')}
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
						{t(side.eyebrow)}
					</p>
					<h3 class="mt-2 text-display-md font-semibold tracking-tight text-fg">{t(side.title)}</h3>
					<ul class="mt-6 flex flex-col gap-3">
						{#each side.points as point (point)}
							<li class="flex items-start gap-3 text-fg-secondary">
								<span
									class="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400"
								>
									<Icon name="check" class="size-3" />
								</span>
								{t(point)}
							</li>
						{/each}
					</ul>
					<div class="mt-8 pt-2">
						<Button
							variant={side.href === '/register' ? 'primary' : 'outline'}
							href={side.href === '/register'
								? `${resolve('/register')}?as=business`
								: resolve(side.href)}
						>
							{t(side.cta)}
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
				eyebrow={t("What's inside")}
				title={t('The tools a front desk actually uses')}
				subtitle={t('Each piece works on its own, and better together.')}
			/>
			<Button variant="ghost" href={resolve('/features')}>
				{t('All features')}
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
					<h3 class="mt-5 font-semibold text-fg">{t(feature.title)}</h3>
					<p class="mt-2 text-sm text-fg-muted">{t(feature.body)}</p>
				</BentoCard>
			{/each}
		</BentoGrid>
	</Container>
</Section>

<!-- How it works -->
<Section>
	<Container size="xl">
		<SectionHeading align="center" eyebrow={t('How it works')} title={t('Live in an afternoon')} />
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
					<h3 class="mt-5 font-semibold text-fg">{t(item.title)}</h3>
					<p class="mt-2 text-sm text-fg-muted">{t(item.body)}</p>
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
			{t('Your next customer is already looking.')}
		</h2>
		<p class="mx-auto mt-4 max-w-xl text-body-lg text-white/80">
			{t('Give them a faster way to find you, book and stay connected.')}
		</p>
		<div class="mt-8 flex flex-wrap justify-center gap-3">
			<Button size="lg" variant="inverse" href={`${resolve('/register')}?as=business`}
				>{t('Start free trial')}</Button
			>
			<Button size="lg" variant="outline-inverse" href={resolve('/pricing')}
				>{t('See pricing')}</Button
			>
		</div>
	</Container>
</Section>
