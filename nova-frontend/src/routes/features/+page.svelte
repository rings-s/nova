<script>
	import { resolve } from '$app/paths';
	import Button from '$lib/components/ui/Button.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import Section from '$lib/components/marketing/Section.svelte';
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';

	/** @type {{ icon: import('$lib/components/ui/Icon.svelte').IconName, number: string, title: string, body: string, points: string[], label: string }[]} */
	const sections = [
		{
			number: '01',
			icon: 'calendar',
			label: 'Smart scheduling',
			title: 'Appointments that never collide.',
			body: 'NOVA calculates availability across providers, services and branches in real time. A slot is temporarily reserved the moment checkout begins, preventing double bookings before they happen.',
			points: [
				'Per-provider schedules and skills',
				'Real-time availability calculation',
				'Temporary checkout holds'
			]
		},
		{
			number: '02',
			icon: 'users',
			label: 'Queue management',
			title: 'Turn waiting into a system.',
			body: 'Appointments and walk-ins operate from the same operational layer. Your front desk sees exactly who is next, who is waiting and what needs attention.',
			points: [
				'Unified booking and walk-in queue',
				'Live customer position',
				'One-click call-next workflow'
			]
		},
		{
			number: '03',
			icon: 'chat-bubble',
			label: 'Customer communication',
			title: 'Meet customers where they already are.',
			body: 'Keep customers informed through WhatsApp without forcing them into another application. Confirmations, reminders and receipts become part of the booking experience.',
			points: ['Automatic confirmations', 'Appointment reminders', 'Receipts and booking updates']
		},
		{
			number: '04',
			icon: 'credit-card',
			label: 'Payments',
			title: 'Protect every appointment.',
			body: 'Require a configurable deposit before confirming a booking. Payments are securely processed through Moyasar while NOVA keeps your booking state synchronized.',
			points: [
				'Configurable deposit percentage',
				'Moyasar payment processing',
				'Clear payment state per booking'
			]
		},
		{
			number: '05',
			icon: 'globe',
			label: 'Discovery',
			title: 'Give your business another front door.',
			body: 'Businesses can opt into the NOVA marketplace and become discoverable by customers searching for services, locations and availability.',
			points: [
				'Search by city and service',
				'Public business storefront',
				'Booking referral tracking'
			]
		},
		{
			number: '06',
			icon: 'sparkles',
			label: 'Intelligence',
			title: 'Ask your business anything.',
			body: 'The NOVA assistant lets staff interact with operational data using natural language. Responses are grounded in real tool results instead of invented numbers.',
			points: [
				'Grounded in your business data',
				'Role-based access',
				'Actions require staff confirmation'
			]
		},
		{
			number: '07',
			icon: 'shield-check',
			label: 'Local by design',
			title: 'Built for Arabic and English from day one.',
			body: 'Every important business record can carry Arabic and English values from its first creation. NOVA is designed around the operational reality of businesses in the region.',
			points: [
				'Arabic and English records',
				'RTL and LTR ready',
				'Designed for regional businesses'
			]
		}
	];

	/** @type {{ n: number, label: string, s: string, t: 'accent'|'info'|'neutral' }[]} */
	const queueSample = [
		{ n: 1, label: 'Noura A.', s: 'In service', t: 'accent' },
		{ n: 2, label: 'Sara M.', s: 'Called', t: 'info' },
		{ n: 3, label: 'Reem K.', s: 'Waiting', t: 'neutral' },
		{ n: 4, label: 'Huda S.', s: 'Waiting', t: 'neutral' }
	];
</script>

<svelte:head>
	<title>Features — NOVA</title>
	<meta
		name="description"
		content="Booking, queues, payments, messaging and business intelligence in one platform."
	/>
</svelte:head>

<!-- Hero -->
<section class="relative isolate overflow-hidden border-b border-line">
	<GradientBlob variant="hero" />
	<Container size="lg" class="py-20 text-center sm:py-28">
		<p
			class="inline-flex items-center gap-2 rounded-full border border-line bg-surface/80 px-3 py-1 text-xs font-medium text-fg-secondary backdrop-blur"
		>
			<span class="size-1.5 rounded-full bg-brand-500"></span>
			The NOVA platform
		</p>
		<h1 class="mx-auto mt-6 max-w-4xl text-display-2xl font-semibold tracking-tight text-fg">
			One operating system for
			<span
				class="text-transparent"
				style="background-image: var(--gradient-hero); -webkit-background-clip: text; background-clip: text;"
				>your front desk.</span
			>
		</h1>
		<p class="mx-auto mt-6 max-w-2xl text-body-lg text-fg-muted">
			Bookings, queues, customer messages, payments and insight — designed to work together instead
			of becoming another collection of disconnected tools.
		</p>
		<div class="mt-9 flex flex-wrap justify-center gap-3">
			<Button size="lg" href={`${resolve('/register')}?as=business`}>Start free trial</Button>
			<Button size="lg" variant="outline" href={resolve('/pricing')}>
				See pricing
				<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
			</Button>
		</div>

		<!-- Section index -->
		<nav class="mx-auto mt-14 flex max-w-4xl flex-wrap justify-center gap-2" aria-label="Features">
			{#each sections as section (section.number)}
				<a
					href={`#feature-${section.number}`}
					class="inline-flex h-8 items-center gap-2 rounded-full border border-line bg-surface px-3.5 text-xs font-medium text-fg-secondary focus-ring transition-colors hover:border-line-strong hover:text-fg"
				>
					<Icon name={section.icon} class="size-3.5 text-accent" />
					{section.label}
				</a>
			{/each}
		</nav>
	</Container>
</section>

<!-- One illustration per feature, built from the app's own components. -->
{#snippet visual(/** @type {string} */ number)}
	{#if number === '01'}
		<div class="space-y-3">
			<p class="text-xs font-semibold tracking-wider text-fg-subtle uppercase">Tuesday · Morning</p>
			<div class="grid grid-cols-3 gap-2">
				{#each ['09:00', '09:30', '10:00', '10:30', '11:00', '11:30'] as time, index (time)}
					<span
						class={[
							'flex h-10 items-center justify-center rounded-control border text-sm font-medium tabular-nums',
							index === 2
								? 'border-brand-600 bg-brand-600 text-white shadow-glow'
								: index === 4
									? 'border-line bg-surface-sunken text-fg-subtle line-through'
									: 'border-line-strong bg-surface text-fg'
						].join(' ')}>{time}</span
					>
				{/each}
			</div>
			<div
				class="flex items-center gap-2 rounded-control bg-accent-soft px-3 py-2 text-xs text-accent"
			>
				<Icon name="clock" class="size-4" />
				10:00 held for you · 9:42 left
			</div>
		</div>
	{:else if number === '02'}
		<ul class="space-y-2">
			{#each queueSample as row (row.n)}
				<li
					class="flex items-center gap-3 rounded-control border border-line bg-surface px-3 py-2.5"
				>
					<span
						class={`flex size-8 items-center justify-center rounded-full text-xs font-semibold tabular-nums ${row.n === 1 ? 'bg-brand-600 text-white' : 'bg-surface-muted text-fg'}`}
						>{row.n}</span
					>
					<span class="flex-1 text-sm font-medium text-fg">{row.label}</span>
					<Badge tone={row.t} size="sm" dot>{row.s}</Badge>
				</li>
			{/each}
		</ul>
	{:else if number === '03'}
		<div class="mx-auto max-w-xs space-y-2">
			<div
				class="rounded-card rounded-ss-sm bg-emerald-600 px-4 py-3 text-sm text-white shadow-card"
			>
				<p class="font-semibold">Lumière Spa</p>
				<p class="mt-1 text-white/90">
					Your facial is confirmed for Tue 10:00 at Olaya branch. Reply 1 to reschedule.
				</p>
				<p class="mt-1 text-end text-[10px] text-white/70">09:41 ✓✓</p>
			</div>
			<div
				class="ms-auto w-fit rounded-card rounded-se-sm bg-surface px-4 py-2 text-sm text-fg shadow-card"
			>
				Thank you!
			</div>
		</div>
	{:else if number === '04'}
		<div class="mx-auto max-w-xs rounded-card border border-line bg-surface p-4 shadow-card">
			<div class="flex justify-between text-sm">
				<span class="text-fg-muted">Signature facial</span><span
					class="font-medium text-fg tabular-nums">SAR 350</span
				>
			</div>
			<div class="mt-2 flex justify-between text-sm">
				<span class="text-fg-muted">Deposit (30%)</span><span
					class="font-semibold text-fg tabular-nums">SAR 105</span
				>
			</div>
			<div
				class="mt-4 flex h-10 items-center justify-center rounded-control bg-slate-900 text-sm font-medium text-white dark:bg-white dark:text-slate-900"
			>
				Pay with Apple Pay
			</div>
			<p class="mt-2 text-center text-[11px] text-fg-muted">Mada · Visa · Mastercard via Moyasar</p>
		</div>
	{:else if number === '05'}
		<div class="space-y-2">
			<div
				class="flex h-10 items-center gap-2 rounded-control border border-line-strong bg-surface px-3 text-sm text-fg-subtle"
			>
				<Icon name="search" class="size-4" /> Hammam in Riyadh
			</div>
			{#each [['Lumière Spa', 'Olaya · 1.2 km', 'SAR 180'], ['Rose Hammam', 'Al Malqa · 3.4 km', 'SAR 220']] as row (row[0])}
				<div
					class="flex items-center justify-between rounded-control border border-line bg-surface px-3 py-2.5"
				>
					<div>
						<p class="text-sm font-semibold text-fg">{row[0]}</p>
						<p class="text-xs text-fg-muted">{row[1]}</p>
					</div>
					<span class="text-sm font-semibold text-fg tabular-nums">{row[2]}</span>
				</div>
			{/each}
		</div>
	{:else if number === '06'}
		<div class="space-y-2">
			<div
				class="ms-auto w-fit max-w-[85%] rounded-card rounded-se-sm bg-brand-600 px-4 py-2 text-sm text-white"
			>
				How did Olaya do last week?
			</div>
			<div
				class="w-fit max-w-[90%] rounded-card rounded-ss-sm border border-line bg-surface px-4 py-3 text-sm text-fg shadow-card"
			>
				Revenue was <span class="font-semibold">SAR 18,420</span>, up 12%. Tuesday mornings were 86%
				booked.
				<p class="mt-2 inline-flex items-center gap-1 text-[11px] text-fg-muted">
					<Icon name="chart-bar" class="size-3" /> From the revenue report
				</p>
			</div>
		</div>
	{:else}
		<div class="grid grid-cols-2 gap-2 text-sm">
			<div class="rounded-control border border-line bg-surface p-3">
				<p class="text-[11px] text-fg-muted">English</p>
				<p class="mt-1 font-semibold text-fg">Signature facial</p>
			</div>
			<div class="rounded-control border border-line bg-surface p-3" dir="rtl" lang="ar">
				<p class="text-[11px] text-fg-muted">العربية</p>
				<p class="mt-1 font-semibold text-fg">فيشل مميز</p>
			</div>
		</div>
	{/if}
{/snippet}

{#each sections as section, i (section.title)}
	<Section tone={i % 2 === 0 ? 'canvas' : 'sunken'}>
		<Container size="lg" id={`feature-${section.number}`} class="scroll-mt-24">
			<div class="grid items-center gap-12 lg:grid-cols-2 lg:gap-20">
				<div class={i % 2 === 1 ? 'lg:order-2' : ''}>
					<p class="flex items-center gap-3 text-xs font-semibold tracking-wider uppercase">
						<span class="text-accent tabular-nums">{section.number}</span>
						<span class="h-px w-8 bg-line-strong" aria-hidden="true"></span>
						<span class="text-fg-muted">{section.label}</span>
					</p>
					<h2 class="mt-5 max-w-xl text-display-lg font-semibold tracking-tight text-fg">
						{section.title}
					</h2>
					<p class="mt-5 max-w-xl text-body-lg text-fg-muted">{section.body}</p>
					<ul class="mt-8 space-y-3">
						{#each section.points as point (point)}
							<li class="flex items-center gap-3 text-sm font-medium text-fg-secondary">
								<span
									class="flex size-6 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent"
								>
									<Icon name="check" class="size-3.5" />
								</span>
								{point}
							</li>
						{/each}
					</ul>
				</div>

				<div class={i % 2 === 1 ? 'lg:order-1' : ''} aria-hidden="true">
					<div
						class="rounded-panel border border-line bg-surface/70 p-2 shadow-raised backdrop-blur"
					>
						<div
							class="relative overflow-hidden rounded-[calc(var(--radius-panel)-0.5rem)] bg-surface-sunken p-6 sm:p-10"
						>
							<div class="mb-6 flex items-center gap-3">
								<span
									class="flex size-9 items-center justify-center rounded-control bg-accent-soft text-accent"
								>
									<Icon name={section.icon} class="size-[18px]" />
								</span>
								<span class="text-sm font-semibold text-fg">{section.label}</span>
							</div>
							{@render visual(section.number)}
						</div>
					</div>
				</div>
			</div>
		</Container>
	</Section>
{/each}

<Section
	tone="dark"
	padding="tight"
	class="mx-4 my-16 rounded-panel sm:mx-6 lg:mx-auto lg:max-w-7xl"
>
	<GradientBlob variant="corner" />
	<Container size="md" class="relative py-8 text-center sm:py-12">
		<h2 class="text-display-lg font-semibold tracking-tight text-white">
			Your next customer is already looking.
		</h2>
		<p class="mx-auto mt-4 max-w-xl text-body-lg text-white/80">
			Give them a faster way to discover your business, book a service and stay connected.
		</p>
		<div class="mt-8 flex justify-center">
			<Button size="lg" variant="inverse" href={`${resolve('/register')}?as=business`}>
				Start with NOVA
				<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
			</Button>
		</div>
		<p class="mt-5 text-xs text-white/60">No credit card required · Set up in minutes</p>
	</Container>
</Section>
