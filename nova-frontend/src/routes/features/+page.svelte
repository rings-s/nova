
<script>
	import { resolve } from '$app/paths';
	import Button from '$lib/components/ui/Button.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import Section from '$lib/components/marketing/Section.svelte';

	/** @type {{ icon: import('$lib/components/ui/Icon.svelte').IconName, number: string, title: string, body: string, points: string[], label: string }[]} */
	const sections = [
		{
			number: '01',
			icon: 'calendar',
			label: 'SMART SCHEDULING',
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
			label: 'QUEUE MANAGEMENT',
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
			label: 'CUSTOMER COMMUNICATION',
			title: 'Meet customers where they already are.',
			body: 'Keep customers informed through WhatsApp without forcing them into another application. Confirmations, reminders and receipts become part of the booking experience.',
			points: [
				'Automatic confirmations',
				'Appointment reminders',
				'Receipts and booking updates'
			]
		},
		{
			number: '04',
			icon: 'credit-card',
			label: 'PAYMENTS',
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
			label: 'DISCOVERY',
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
			label: 'INTELLIGENCE',
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
			label: 'LOCAL BY DESIGN',
			title: 'Built for Arabic and English from day one.',
			body: 'Every important business record can carry Arabic and English values from its first creation. NOVA is designed around the operational reality of businesses in the region.',
			points: [
				'Arabic and English records',
				'RTL and LTR ready',
				'Designed for regional businesses'
			]
		}
	];
</script>

<svelte:head>
	<title>Features — NOVA</title>
	<meta
		name="description"
		content="Booking, queues, payments, messaging and business intelligence in one platform."
	/>
</svelte:head>

<!-- HERO -->
<Section tone="canvas" padding="tight" class="relative overflow-hidden">
	<!-- Ambient lighting -->
	<div
		class="pointer-events-none absolute left-1/2 top-0 h-[500px] w-[800px] -translate-x-1/2 rounded-full bg-brand-500/[0.08] blur-[120px]"
	></div>

	<div
		class="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand-500/40 to-transparent"
	></div>

	<Container size="lg" class="relative">
		<div class="mx-auto max-w-4xl text-center">
			<div
				class="mb-7 inline-flex items-center gap-2 rounded-full border border-slate-200/80 bg-white/70 px-3 py-1.5 text-[11px] font-semibold tracking-[0.18em] text-slate-500 uppercase shadow-sm backdrop-blur dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-400"
			>
				<span class="size-1.5 rounded-full bg-brand-500"></span>
				NOVA PLATFORM
			</div>

			<h1
				class="text-display-xl font-semibold tracking-[-0.04em] text-slate-950 dark:text-white"
			>
				One operating system for
				<span
					class="bg-gradient-to-r from-brand-500 via-brand-600 to-violet-500 bg-clip-text text-transparent"
				>
					your front desk.
				</span>
			</h1>

			<p
				class="mx-auto mt-7 max-w-2xl text-body-lg leading-relaxed text-slate-600 dark:text-slate-400"
			>
				Bookings, queues, customer communication, payments and intelligence —
				designed to work together instead of becoming another collection of disconnected tools.
			</p>

			<div class="mt-9 flex flex-wrap justify-center gap-3">
				<Button size="lg" href={resolve('/register')}>Get started</Button>

				<Button size="lg" variant="ghost" href={resolve('/demo')}>
					See the platform
					<Icon name="arrow-right" class="ml-1 size-4" />
				</Button>
			</div>
		</div>

		<!-- Product preview -->
		<div class="relative mx-auto mt-20 max-w-5xl">
			<div
				class="absolute -inset-10 -z-10 rounded-[4rem] bg-brand-500/[0.06] blur-3xl"
			></div>

			<div
				class="overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-[0_40px_100px_-30px_rgba(15,23,42,0.25)] dark:border-white/10 dark:bg-slate-950 dark:shadow-black/40"
			>
				<!-- Window chrome -->
				<div
					class="flex h-12 items-center border-b border-slate-200 px-5 dark:border-white/10"
				>
					<div class="flex gap-1.5">
						<span class="size-2.5 rounded-full bg-slate-200 dark:bg-white/10"></span>
						<span class="size-2.5 rounded-full bg-slate-200 dark:bg-white/10"></span>
						<span class="size-2.5 rounded-full bg-slate-200 dark:bg-white/10"></span>
					</div>

					<div
						class="mx-auto rounded-lg bg-slate-100 px-5 py-1 text-[10px] font-medium text-slate-400 dark:bg-white/[0.04]"
					>
						app.nova.sa
					</div>

					<div class="w-12"></div>
				</div>

				<!-- Dashboard preview -->
				<div class="grid min-h-[330px] grid-cols-[90px_1fr] sm:grid-cols-[150px_1fr]">
					<div class="border-r border-slate-200 p-4 dark:border-white/10">
						<div class="mb-8 h-6 w-16 rounded bg-slate-100 dark:bg-white/[0.06]"></div>

						<div class="space-y-3">
							{#each Array(5) as _, index}
								<div
									class="h-8 rounded-lg {index === 0
										? 'bg-brand-500/10'
										: 'bg-slate-50 dark:bg-white/[0.025]'}"
								></div>
							{/each}
						</div>
					</div>

					<div class="p-5 sm:p-7">
						<div class="flex items-center justify-between">
							<div>
								<div class="h-3 w-20 rounded bg-slate-200 dark:bg-white/10"></div>
								<div class="mt-2 h-6 w-36 rounded bg-slate-900/10 dark:bg-white/10"></div>
							</div>

							<div class="h-9 w-24 rounded-lg bg-brand-500"></div>
						</div>

						<div class="mt-7 grid gap-3 sm:grid-cols-3">
							{#each [
								['Bookings', '128'],
								['Waiting', '07'],
								['Revenue', '24.8K']
							] as stat}
								<div
									class="rounded-xl border border-slate-200 p-4 dark:border-white/10"
								>
									<div class="text-[10px] font-medium text-slate-400">{stat[0]}</div>
									<div
										class="mt-2 text-xl font-semibold tracking-tight text-slate-900 dark:text-white"
									>
										{stat[1]}
									</div>
								</div>
							{/each}
						</div>

						<div
							class="mt-4 grid min-h-[130px] grid-cols-5 items-end gap-2 rounded-xl border border-slate-200 p-5 dark:border-white/10"
						>
							{#each [35, 55, 42, 75, 62, 88, 68, 94, 78, 100] as height}
								<div
									class="rounded-t bg-gradient-to-t from-brand-600/20 to-brand-500/70"
									style={`height:${height}%`}
								></div>
							{/each}
						</div>
					</div>
				</div>
			</div>
		</div>
	</Container>
</Section>

<!-- FEATURES -->
{#each sections as section, i (section.title)}
	<Section tone={i % 2 === 0 ? 'canvas' : 'sunken'} class="relative overflow-hidden">
		<!-- Section number -->
		<div
			class="pointer-events-none absolute right-[-2rem] top-1/2 hidden -translate-y-1/2 text-[18rem] font-bold leading-none tracking-[-0.08em] text-slate-950/[0.025] lg:block dark:text-white/[0.025]"
		>
			{section.number}
		</div>

		<Container size="lg" class="relative">
			<div class="grid items-center gap-14 lg:grid-cols-2 lg:gap-24">
				<!-- Copy -->
				<div class={i % 2 === 1 ? 'lg:order-2' : ''}>
					<div class="flex items-center gap-3">
						<span
							class="font-mono text-xs font-semibold tracking-[0.2em] text-brand-600 dark:text-brand-400"
						>
							{section.number}
						</span>

						<span class="h-px w-8 bg-brand-500/40"></span>

						<span
							class="text-[10px] font-semibold tracking-[0.18em] text-slate-400 uppercase"
						>
							{section.label}
						</span>
					</div>

					<h2
						class="mt-6 max-w-xl text-display-lg font-semibold tracking-[-0.035em] text-slate-950 dark:text-white"
					>
						{section.title}
					</h2>

					<p
						class="mt-6 max-w-xl text-body-lg leading-relaxed text-slate-600 dark:text-slate-400"
					>
						{section.body}
					</p>

					<ul class="mt-8 space-y-3">
						{#each section.points as point (point)}
							<li class="flex items-center gap-3">
								<span
									class="flex size-6 shrink-0 items-center justify-center rounded-full border border-brand-500/20 bg-brand-500/10 text-brand-600 dark:text-brand-400"
								>
									<Icon name="check" class="size-3.5" />
								</span>

								<span class="text-sm font-medium text-slate-700 dark:text-slate-300">
									{point}
								</span>
							</li>
						{/each}
					</ul>
				</div>

				<!-- Visual -->
				<div class={i % 2 === 1 ? 'lg:order-1' : ''}>
					<div class="group relative">
						<!-- Glow -->
						<div
							class="absolute -inset-5 rounded-[3rem] bg-brand-500/[0.06] opacity-0 blur-2xl transition duration-700 group-hover:opacity-100"
						></div>

						<div
							class="relative overflow-hidden rounded-[2rem] border border-slate-200/80 bg-white/80 p-3 shadow-[0_30px_80px_-35px_rgba(15,23,42,0.3)] backdrop-blur-xl transition duration-500 group-hover:-translate-y-1 group-hover:shadow-[0_40px_100px_-35px_rgba(15,23,42,0.4)] dark:border-white/10 dark:bg-white/[0.035] dark:shadow-black/30"
						>
							<!-- Inner panel -->
							<div
								class="relative flex aspect-[4/3] items-center justify-center overflow-hidden rounded-[1.5rem] bg-slate-50 dark:bg-slate-900"
							>
								<!-- Decorative grid -->
								<div
									class="absolute inset-0 opacity-[0.35] dark:opacity-[0.15]"
									style="background-image: linear-gradient(to right, rgb(148 163 184 / 0.12) 1px, transparent 1px), linear-gradient(to bottom, rgb(148 163 184 / 0.12) 1px, transparent 1px); background-size: 32px 32px;"
								></div>

								<!-- Radial glow -->
								<div
									class="absolute left-1/2 top-1/2 size-64 -translate-x-1/2 -translate-y-1/2 rounded-full bg-brand-500/10 blur-3xl"
								></div>

								<!-- Main icon -->
								<div class="relative">
									<div
										class="absolute -inset-8 rounded-full border border-brand-500/10"
									></div>

									<div
										class="absolute -inset-14 rounded-full border border-brand-500/[0.06]"
									></div>

									<div
										class="relative flex size-24 items-center justify-center rounded-[1.75rem] border border-white/80 bg-white shadow-xl shadow-slate-900/10 dark:border-white/10 dark:bg-slate-800 dark:shadow-black/30"
									>
										<Icon
											name={section.icon}
											class="size-10 text-brand-500"
										/>
									</div>
								</div>

								<!-- Floating data chips -->
								<div
									class="absolute left-5 top-5 rounded-xl border border-slate-200 bg-white/90 px-3 py-2 shadow-lg backdrop-blur dark:border-white/10 dark:bg-slate-800/90"
								>
									<div class="flex items-center gap-2">
										<span class="size-1.5 rounded-full bg-emerald-500"></span>
										<span
											class="text-[10px] font-semibold tracking-wide text-slate-500 dark:text-slate-400"
										>
											LIVE
										</span>
									</div>
								</div>

								<div
									class="absolute bottom-5 right-5 rounded-xl border border-slate-200 bg-white/90 px-3 py-2 shadow-lg backdrop-blur dark:border-white/10 dark:bg-slate-800/90"
								>
									<div class="text-[9px] text-slate-400">NOVA</div>
									<div class="mt-0.5 text-xs font-semibold text-slate-800 dark:text-white">
										Connected
									</div>
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>
		</Container>
	</Section>
{/each}

<!-- FINAL CTA -->
<Section tone="dark" class="relative overflow-hidden">
	<div
		class="pointer-events-none absolute left-1/2 top-1/2 size-[500px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-brand-500/10 blur-[120px]"
	></div>

	<Container size="md" class="relative text-center">
		<div
			class="mx-auto mb-6 flex size-12 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.06]"
		>
			<Icon name="sparkles" class="size-5 text-brand-400" />
		</div>

		<h2 class="text-display-lg font-semibold tracking-[-0.035em] text-white">
			Your next customer is already looking.
		</h2>

		<p class="mx-auto mt-5 max-w-xl text-body-lg leading-relaxed text-white/60">
			Give them a faster way to discover your business, book a service and stay connected.
		</p>

		<div class="mt-9 flex justify-center">
			<Button size="lg" variant="inverse" href={resolve('/register')}>
				Start with NOVA
				<Icon name="arrow-right" class="ml-1 size-4" />
			</Button>
		</div>

		<p class="mt-5 text-xs text-white/40">
			No credit card required · Set up in minutes
		</p>
	</Container>
</Section>
