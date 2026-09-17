<script>
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import Button from '$lib/components/ui/Button.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import Section from '$lib/components/marketing/Section.svelte';
	import SectionHeading from '$lib/components/marketing/SectionHeading.svelte';
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';
	import BentoGrid from '$lib/components/marketing/BentoGrid.svelte';
	import BentoCard from '$lib/components/marketing/BentoCard.svelte';

	/** @type {{ icon: import('$lib/components/ui/Icon.svelte').IconName, title: string, body: string, span?: 1|2 }[]} */
	const capabilities = [
		{
			icon: 'calendar',
			title: 'Booking that never double-books',
			body: 'Deterministic availability across every branch and provider, with a slot held while checkout completes.',
			span: 2
		},
		{
			icon: 'users',
			title: 'Walk-ins, handled',
			body: 'A QR ticket at the door shares one line with appointments — no separate calendars to reconcile.'
		},
		{
			icon: 'chat-bubble',
			title: 'WhatsApp, not another app',
			body: 'Confirmations, reminders and receipts land where your customers already are.'
		},
		{
			icon: 'credit-card',
			title: 'Deposits & payments',
			body: 'Take a deposit to confirm a booking, with Moyasar handling the card details.'
		},
		{
			icon: 'sparkles',
			title: 'An AI assistant on staff',
			body: 'A chat assistant your team can ask about bookings, revenue and schedules — grounded in your own data.'
		}
	];

	/** @type {{ icon: import('$lib/components/ui/Icon.svelte').IconName, title: string, body: string }[]} */
	const gccValues = [
		{
			icon: 'globe',
			title: 'Bilingual by design',
			body: 'Every business, service and booking is Arabic and English from the first record, not a translated afterthought.'
		},
		{
			icon: 'chat-bubble',
			title: 'WhatsApp-native',
			body: 'The channel your customers already check, built into the booking flow itself.'
		},
		{
			icon: 'credit-card',
			title: 'SAR, Riyadh time',
			body: 'Pricing, schedules and payouts default to the GCC — not adapted from a template built for somewhere else.'
		}
	];
</script>

<svelte:head><title>NOVA — Booking for salons and spas</title></svelte:head>

{#if authStore.isAuthenticated}
	<Container size="lg" class="py-16 sm:py-24">
		<h1 class="text-display-md font-semibold text-slate-900 dark:text-slate-100">Welcome back</h1>
		{#if authStore.isStaff}
			<p class="mt-2 text-slate-500 dark:text-slate-400">
				Switch businesses from the header, or pick up where you left off.
			</p>
			<Button class="mt-4" href={resolve('/app')}>Go to dashboard</Button>
		{:else}
			<p class="mt-2 text-slate-500 dark:text-slate-400">Your bookings will show up here.</p>
			<div class="mt-4 flex flex-wrap gap-3">
				<Button href={resolve('/bookings')}>My bookings</Button>
				<Button variant="outline" href={resolve('/discover')}>Find a salon</Button>
			</div>
		{/if}
	</Container>
{:else}
	<Section tone="canvas">
		<GradientBlob variant="hero" />
		<Container size="xl">
			<div class="grid items-center gap-12 lg:grid-cols-2">
				<div>
					<p
						class="text-xs font-semibold tracking-wide text-brand-600 uppercase dark:text-brand-400"
					>
						Built for GCC salons &amp; spas
					</p>
					<h1
						class="mt-3 text-display-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100"
					>
						Booking, queues and payments — one platform for your salon.
					</h1>
					<p class="mt-6 text-body-lg text-slate-600 dark:text-slate-400">
						NOVA brings appointments, walk-ins and WhatsApp messaging together for beauty and
						wellness businesses across the GCC.
					</p>
					<div class="mt-8 flex flex-wrap gap-3">
						<Button size="lg" href={resolve('/register')}>Get started</Button>
						<Button size="lg" variant="outline" href={resolve('/discover')}>Find a salon</Button>
					</div>
				</div>

				<div class="relative hidden lg:block" aria-hidden="true">
					<div
						class="hero-glow-layer absolute inset-0 rounded-3xl opacity-20 blur-sm"
						style="background-image: var(--gradient-hero)"
					></div>
					<div
						class="hero-card relative -rotate-2 rounded-3xl border border-slate-200/80 bg-white/90 p-6 backdrop-blur dark:border-slate-800/80 dark:bg-slate-900/90"
					>
						<p class="text-xs font-medium text-slate-500 dark:text-slate-400">Today · Riyadh</p>
						<ul class="mt-4 space-y-3">
							<li
								class="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 dark:bg-slate-800/60"
							>
								<span class="text-sm text-slate-700 dark:text-slate-200"
									>10:30 — Haircut &amp; style</span
								>
								<Badge tone="success" size="sm">Confirmed</Badge>
							</li>
							<li
								class="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 dark:bg-slate-800/60"
							>
								<span class="text-sm text-slate-700 dark:text-slate-200"
									>11:15 — Walk-in, ticket #4</span
								>
								<Badge tone="info" size="sm">Waiting</Badge>
							</li>
							<li
								class="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 dark:bg-slate-800/60"
							>
								<span class="text-sm text-slate-700 dark:text-slate-200"
									>12:00 — Deposit received</span
								>
								<Badge tone="accent" size="sm">SAR 50</Badge>
							</li>
						</ul>
					</div>
				</div>
			</div>
		</Container>
	</Section>

	<Section tone="canvas">
		<Container size="xl">
			<SectionHeading
				eyebrow="Everything in one place"
				title="Run the front desk from a single screen"
				subtitle="No separate calendar, queue board, messaging tool and payment link to keep in sync."
			/>
			<BentoGrid class="mt-12">
				{#each capabilities as item (item.title)}
					<BentoCard span={item.span ?? 1}>
						<div
							class="inline-flex size-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-950/40 dark:text-brand-400"
						>
							<Icon name={item.icon} class="size-6" />
						</div>
						<h3 class="mt-4 font-semibold text-slate-900 dark:text-slate-100">{item.title}</h3>
						<p class="mt-2 text-sm text-slate-500 dark:text-slate-400">{item.body}</p>
					</BentoCard>
				{/each}
			</BentoGrid>
		</Container>
	</Section>

	<Section tone="sunken">
		<GradientBlob variant="soft" />
		<Container size="lg">
			<SectionHeading
				align="center"
				eyebrow="Why NOVA"
				title="Built for the GCC, not adapted for it"
				subtitle="The details a template built elsewhere gets wrong by default."
			/>
			<div class="mt-12 grid gap-8 sm:grid-cols-3">
				{#each gccValues as item (item.title)}
					<div class="text-center">
						<div
							class="mx-auto inline-flex size-12 items-center justify-center rounded-full bg-white text-brand-600 shadow-sm dark:bg-slate-900 dark:text-brand-400"
						>
							<Icon name={item.icon} class="size-6" />
						</div>
						<h3 class="mt-4 font-semibold text-slate-900 dark:text-slate-100">{item.title}</h3>
						<p class="mt-2 text-sm text-slate-500 dark:text-slate-400">{item.body}</p>
					</div>
				{/each}
			</div>
		</Container>
	</Section>

	<Section tone="dark">
		<Container size="md" class="text-center">
			<h2 class="text-display-lg font-semibold tracking-tight">Bring your salon onto NOVA</h2>
			<p class="mt-4 text-body-lg text-white/80">
				Set up your storefront, services and providers in minutes.
			</p>
			<div class="mt-8 flex justify-center">
				<Button size="lg" variant="inverse" href={resolve('/register')}>Get started</Button>
			</div>
		</Container>
	</Section>
{/if}

<style>
	/*
	 * The hero mockup card's shadow breathes slowly between a neutral
	 * elevation shadow and a warm brand-tinted glow, and the gradient layer
	 * behind it drifts in rotation — the same "ambient, not distracting"
	 * treatment as GradientBlob. Scoped to this page only.
	 *
	 * Uses `transform`/`box-shadow` (not the newer standalone `translate`/
	 * `scale`/`rotate` properties) for the same reason GradientBlob does:
	 * broad browser support, including Safari before 16.4.
	 */
	@keyframes hero-card-glow {
		0%,
		100% {
			box-shadow: 0 25px 50px -12px rgb(0 0 0 / 0.25);
		}
		50% {
			box-shadow: 0 25px 60px -8px color-mix(in oklch, var(--color-brand-500) 45%, transparent);
		}
	}
	@keyframes hero-glow-drift {
		0%,
		100% {
			transform: rotate(3deg);
		}
		50% {
			transform: rotate(7deg);
		}
	}

	.hero-card {
		animation: hero-card-glow 7s ease-in-out infinite;
	}
	.hero-glow-layer {
		animation: hero-glow-drift 9s ease-in-out infinite;
	}

	@media (prefers-reduced-motion: reduce) {
		.hero-card,
		.hero-glow-layer {
			animation: none;
		}
	}
</style>
