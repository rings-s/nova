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
	import Icon from '$lib/components/ui/Icon.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import Section from '$lib/components/marketing/Section.svelte';
	import SectionHeading from '$lib/components/marketing/SectionHeading.svelte';
	import BentoGrid from '$lib/components/marketing/BentoGrid.svelte';
	import BentoCard from '$lib/components/marketing/BentoCard.svelte';
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';
	import HeroPreview from '$lib/components/marketing/HeroPreview.svelte';

	/** @typedef {import('$lib/components/ui/Icon.svelte').IconName} IconName */

	// Split for the word-by-word reveal; Arabic splits on its spaces the same way.
	let titleWords = $derived(t('Beauty and wellness,').split(' '));

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
			eyebrow: m('For salons, spas & clinics'),
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
			cta: m('Book a treatment'),
			href: '/discover'
		}
	];
</script>

<svelte:head>
	<title
		>{t(
			'NOVA — Bookings, queues and payments for GCC salons, spas, massage centres and beauty clinics'
		)}</title
	>
</svelte:head>

<!-- Hero: the whole first screen, below the header (4rem and its 1px border) (`svh`, so a phone's
     browser bars never push it past the fold). -->
<section class="relative isolate flex min-h-[calc(100svh-4rem-1px)] items-center overflow-hidden">
	<GradientBlob variant="hero" />
	<Container
		size="xl"
		class="grid w-full items-center gap-14 py-16 sm:py-20 lg:grid-cols-[1.05fr_1fr]"
	>
		<div>
			<p
				class="hero-badge inline-flex items-center gap-2 rounded-full border border-line bg-surface/80 px-3 py-1 text-xs font-medium text-fg-secondary backdrop-blur"
			>
				<span class="hero-dot relative size-1.5 rounded-full bg-brand-500"></span>
				{t('Built for salons, spas, massage and beauty clinics in the GCC')}
			</p>
			<!-- Each word rises out of its own mask; the gradient phrase lands last. -->
			<h1 class="mt-6 text-display-2xl font-semibold tracking-tight text-fg">
				{#each titleWords as word, i (i)}
					<span class="word"><span class="word-in" style:--d="{120 + i * 85}ms">{word}</span></span>
					<!-- A real space, so the heading reads as words: Svelte trims the template's. -->
					<!-- eslint-disable-next-line svelte/no-useless-mustaches -->
					{' '}
				{/each}
				<span class="word"
					><span class="word-in ink" style:--d="{180 + titleWords.length * 85}ms"
						>{t('beautifully run.')}</span
					></span
				>
			</h1>
			<p class="hero-rise mt-6 max-w-xl text-body-lg text-fg-muted" style:--d="620ms">
				{t(
					'Bookings, walk-ins, staff, payments and customer messages — synchronized in one place, in Arabic and English.'
				)}
			</p>
			<div class="hero-rise mt-9 flex flex-wrap gap-3" style:--d="740ms">
				{#if authStore.isAuthenticated && authStore.isStaff}
					<Button size="lg" href={resolve('/app')} class="sheen">
						{t('Go to dashboard')}
						<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
					</Button>
				{:else}
					<Button size="lg" href={`${resolve('/register')}?as=business`} class="sheen">
						{t('Start free trial')}
						<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
					</Button>
				{/if}
				<Button size="lg" variant="outline" href={resolve('/discover')}>
					<Icon name="search" class="size-4" />
					{t('Book a treatment')}
				</Button>
			</div>
			<p class="hero-rise mt-5 text-xs text-fg-muted" style:--d="860ms">
				{t('7-day free trial · No card required · Cancel anytime')}
			</p>
		</div>

		<!-- Illustrative product preview: a day sheet that runs itself. -->
		<HeroPreview />
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

<style>
	/*
	 * The hero's entrance, as one choreography (~1.5s). Every piece reads its
	 * delay from `--d`, so the order lives in the markup. All of it collapses
	 * to nothing under `prefers-reduced-motion` (routes/layout.css).
	 */
	.hero-badge {
		animation: badge-in 0.7s var(--ease-out-premium) both;
	}
	@keyframes badge-in {
		from {
			opacity: 0;
			transform: translateY(8px) scale(0.94);
		}
	}
	/* The badge's dot breathes, once the page has settled. */
	.hero-dot::after {
		content: '';
		position: absolute;
		inset: 0;
		border-radius: 9999px;
		background: inherit;
		animation: dot-ping 2.4s cubic-bezier(0, 0, 0.2, 1) 1.6s infinite;
	}
	@keyframes dot-ping {
		70%,
		100% {
			transform: scale(3.2);
			opacity: 0;
		}
	}

	/* Each word sits in a mask and rises into it, sharpening as it lands. */
	.word {
		display: inline-block;
		overflow: hidden;
		/* Room for descenders inside the mask, given back to the line. */
		padding-block-end: 0.14em;
		margin-block-end: -0.14em;
		vertical-align: bottom;
	}
	.word-in {
		display: inline-block;
		animation: word-rise 1s var(--ease-out-premium) var(--d, 0ms) both;
	}
	@keyframes word-rise {
		from {
			opacity: 0;
			transform: translateY(105%) rotate(4deg);
			filter: blur(8px);
		}
	}

	/* The gradient phrase: the brand ink, drifting slowly through its colours. */
	.ink {
		color: transparent;
		background-image: var(--gradient-hero);
		background-size: 220% 100%;
		-webkit-background-clip: text;
		background-clip: text;
		animation:
			word-rise 1.1s var(--ease-out-premium) var(--d, 0ms) both,
			ink-drift 9s ease-in-out 2s infinite alternate;
	}
	@keyframes ink-drift {
		from {
			background-position: 0% 50%;
		}
		to {
			background-position: 100% 50%;
		}
	}

	.hero-rise {
		animation: rise 0.9s var(--ease-out-premium) var(--d, 0ms) both;
	}
	@keyframes rise {
		from {
			opacity: 0;
			transform: translateY(14px);
			filter: blur(4px);
		}
	}

	/* One sheen across the primary button, once everything has landed. */
	.hero-rise :global(.sheen) {
		position: relative;
		overflow: hidden;
		isolation: isolate;
	}
	.hero-rise :global(.sheen)::after {
		content: '';
		position: absolute;
		inset: 0;
		background: linear-gradient(
			105deg,
			transparent 30%,
			rgb(255 255 255 / 0.35) 50%,
			transparent 70%
		);
		transform: translateX(-120%);
		animation: sheen 1.1s var(--ease-out-premium) 1.7s both;
		pointer-events: none;
	}
	@keyframes sheen {
		to {
			transform: translateX(120%);
		}
	}
</style>
