<script>
	import { resolve } from '$app/paths';
	import Button from '$lib/components/ui/Button.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import Section from '$lib/components/marketing/Section.svelte';
	import SectionHeading from '$lib/components/marketing/SectionHeading.svelte';
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';

	/** @typedef {'holds'|'bilingual'|'whatsapp'|'banking'} LayerId */

	/** @type {LayerId} */
	let activeLayer = $state('holds');

	/** @type {{ id: LayerId, label: string }[]} */
	const layerTabs = [
		{ id: 'holds', label: '1. Slot holds' },
		{ id: 'bilingual', label: '2. Bilingual data' },
		{ id: 'whatsapp', label: '3. WhatsApp' },
		{ id: 'banking', label: '4. Payments' }
	];

	/** @type {Record<LayerId, { title: string, tag: string, highlight: string, codeSnippet: string, description: string }>} */
	const architectureLayers = {
		holds: {
			title: 'Deterministic slot holds',
			tag: 'Concurrency control',
			highlight: 'A short-lived lock, held per slot',
			codeSnippet: `// Simplified example
await redis.set(
  \`hold:\${tenantId}:\${slotId}\`,
  JSON.stringify({ clientId, expiresAt: Date.now() + 600000 }),
  'EX', 600, 'NX'
);`,
			description:
				'The moment a customer starts checkout, that slot is held for a few minutes in distributed memory. If a walk-in at reception and an online customer reach for the same slot, the first hold wins — never a double-booking.'
		},
		bilingual: {
			title: 'Bilingual by design',
			tag: 'Regional data model',
			highlight: 'Arabic and English on every record',
			codeSnippet: `// Simplified example
type Service = {
  name_ar: 'قص شعر وتصفيف سشوار',
  name_en: 'Signature Blowout & Cut',
  price: 180.00,
  currency: 'SAR'
};`,
			description:
				'Every business, service and provider name is stored in Arabic and English from the first record — not translated after the fact by a client-side overlay that breaks layout or number formatting.'
		},
		whatsapp: {
			title: 'WhatsApp messaging',
			tag: 'Direct messaging',
			highlight: 'Confirmations sent where customers already are',
			codeSnippet: `// Simplified example
POST /v1/messages/template
{
  "template": "booking_confirmed",
  "to": customerPhone,
  "vars": [customerName, startsAt]
}`,
			description:
				'Booking confirmations, reminders and receipts are sent on WhatsApp — built into the booking flow itself, not a separate app a customer has to download.'
		},
		banking: {
			title: 'Deposits & payments',
			tag: 'Financial infrastructure',
			highlight: 'Card details handled by Moyasar, not NOVA',
			codeSnippet: `// Simplified example
POST /v1/payments
{
  "amount": 5000,
  "currency": "SAR",
  "source": { "type": "applepay" }
}`,
			description:
				'A deposit can be required to confirm a booking. Card and Mada details are captured directly by Moyasar — they never pass through or get stored on NOVA servers.'
		}
	};

	let current = $derived(architectureLayers[activeLayer]);

	/** @type {{ icon: import('$lib/components/ui/Icon.svelte').IconName, title: string, subtitle: string, body: string }[]} */
	const pillars = [
		{
			icon: 'globe',
			title: 'Arabic-native data core',
			subtitle: 'Bilingual by design',
			body: 'Every business, service, provider profile, and confirmation message stores Arabic and English data natively from the first record — not a client-side translation layer bolted on afterward.'
		},
		{
			icon: 'calendar',
			title: 'Deterministic slot holds',
			subtitle: 'No double-booking',
			body: 'When a walk-in at reception and an online customer reach for the same slot, NOVA holds it for the first checkout to complete — so the same appointment is never sold twice.'
		},
		{
			icon: 'chat-bubble',
			title: 'WhatsApp as core infrastructure',
			subtitle: 'No forced app downloads',
			body: "Rather than asking clients to install a separate app, NOVA sends confirmations and reminders on WhatsApp — the channel they're already using."
		},
		{
			icon: 'credit-card',
			title: 'GCC financial integration',
			subtitle: 'Moyasar, Mada & Apple Pay',
			body: 'Deposits and payments run through Moyasar, supporting Mada, Apple Pay and card payments. NOVA never holds customer funds or touches card details directly.'
		}
	];

	const comparisons = [
		{
			label: 'Client booking experience',
			legacy:
				'Forces clients to create another account, install a separate mobile app, and set a password.',
			nova: 'A web storefront with card/Apple Pay checkout and automatic confirmations sent via WhatsApp.'
		},
		{
			label: 'Walk-in & appointment queue',
			legacy:
				'A paper notebook on the reception counter that gets out of sync with phone bookings and online slots.',
			nova: 'One unified line for walk-ins and bookings, with a ticket and live queue position.'
		},
		{
			label: 'Language & locale',
			legacy: 'English-only software, with translation overlays that break layout in RTL.',
			nova: 'Arabic and English stored natively on every record, not translated after the fact.'
		},
		{
			label: 'Deposit & no-show protection',
			legacy: 'No deposits, or manual bank transfers coordinated over WhatsApp screenshots.',
			nova: 'A deposit collected at booking time through Moyasar, credited automatically to the bill.'
		}
	];
</script>

<svelte:head>
	<title>About NOVA — Built for the GCC Salon & Spa Industry</title>
	<meta
		name="description"
		content="Learn about NOVA's mission: replacing fragmented salon software with a unified, bilingual operating system engineered for Saudi Arabia and the GCC."
	/>
</svelte:head>

<!-- Master Hero Header -->
<Section
	tone="canvas"
	padding="tight"
	class="relative overflow-hidden pt-8 pb-14 sm:pt-14 sm:pb-20"
>
	<GradientBlob variant="hero" />
	<Container size="xl">
		<!-- Status ribbon -->
		<div class="flex items-center justify-center">
			<div
				class="inline-flex flex-wrap items-center justify-center gap-2 rounded-full border border-slate-200/80 bg-white/90 px-4 py-1.5 text-xs font-semibold text-slate-700 shadow-xs backdrop-blur dark:border-slate-800/80 dark:bg-slate-900/90 dark:text-slate-300"
			>
				<span class="flex items-center gap-1.5">
					<span class="size-2 rounded-full bg-emerald-500"></span>
					<span>Built for the GCC</span>
				</span>
				<span class="text-slate-300 dark:text-slate-700">·</span>
				<span class="font-bold text-brand-600 dark:text-brand-400">Riyadh · Jeddah · Dubai</span>
			</div>
		</div>

		<!-- Core Headline -->
		<div class="mx-auto mt-6 max-w-4xl text-center">
			<h1
				class="text-display-xl font-extrabold tracking-tight text-slate-900 sm:text-display-2xl dark:text-slate-100"
			>
				Built for the reality of GCC salons &amp; spas
			</h1>
			<p class="mx-auto mt-5 max-w-2xl text-body-lg text-slate-600 sm:text-xl dark:text-slate-400">
				Booking, walk-ins, WhatsApp and payments are usually four disconnected tools stitched
				together by hand. NOVA brings them into one platform, built around how a salon actually runs
				its day.
			</p>
			<div class="mt-8 flex flex-wrap items-center justify-center gap-3">
				<Button size="lg" href={resolve('/register')}>Start 14-day free trial</Button>
				<Button size="lg" variant="outline" href={resolve('/features')}>
					Explore OS architecture
				</Button>
			</div>
		</div>

		<!-- Interactive Architecture Stack Viewer -->
		<div
			class="mt-14 overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-900"
		>
			<!-- Stack Header Bar -->
			<div
				class="dark:bg-slate-850 flex flex-wrap items-center justify-between border-b border-slate-200 bg-slate-50/90 px-6 py-3.5 backdrop-blur dark:border-slate-800"
			>
				<div>
					<span class="text-xs font-bold tracking-wider text-slate-500 uppercase">
						System Architecture Blueprint
					</span>
					<p class="text-xs font-semibold text-slate-700 dark:text-slate-300">
						Inspect how NOVA solves core regional salon problems
					</p>
				</div>
				<div
					class="mt-2 flex items-center gap-1 rounded-xl border border-slate-200 bg-white p-1 text-xs font-semibold sm:mt-0 dark:border-slate-700 dark:bg-slate-800"
				>
					{#each layerTabs as tab (tab.id)}
						<button
							type="button"
							onclick={() => (activeLayer = tab.id)}
							class={[
								'rounded-lg px-2.5 py-1 text-xs transition-all',
								activeLayer === tab.id
									? 'bg-slate-900 font-bold text-white dark:bg-slate-100 dark:text-slate-900'
									: 'text-slate-600 hover:text-slate-900 dark:text-slate-400'
							].join(' ')}
						>
							{tab.label}
						</button>
					{/each}
				</div>
			</div>

			<!-- Active architecture details -->
			<div class="grid gap-8 p-6 lg:grid-cols-12">
				<div class="space-y-4 lg:col-span-7">
					<div class="flex items-center gap-2">
						<Badge tone="accent" size="sm">{current.tag}</Badge>
					</div>
					<h3 class="text-xl font-bold text-slate-900 dark:text-slate-100">
						{current.title}
					</h3>
					<p class="text-xs leading-relaxed text-slate-600 dark:text-slate-400">
						{current.description}
					</p>
					<div
						class="rounded-xl border border-slate-200 bg-slate-50 p-3.5 text-xs dark:border-slate-800 dark:bg-slate-800/60"
					>
						<span class="font-semibold text-slate-700 dark:text-slate-300">In short:</span>
						<p class="mt-0.5 text-slate-500 dark:text-slate-400">{current.highlight}</p>
					</div>
				</div>

				<div class="lg:col-span-5">
					<div
						class="overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 p-4 font-mono text-xs text-slate-200 shadow-inner"
					>
						<div
							class="flex items-center justify-between border-b border-slate-800 pb-2 text-[10px] text-slate-400"
						>
							<span>Illustrative example</span>
						</div>
						<pre class="mt-3 overflow-x-auto text-[11px] leading-relaxed text-emerald-400"><code
								>{current.codeSnippet}</code
							></pre>
					</div>
				</div>
			</div>
		</div>
	</Container>
</Section>

<!-- The Problem & Solution Comparison -->
<Section tone="sunken" class="border-y border-slate-200 py-16 sm:py-24 dark:border-slate-800">
	<Container size="xl">
		<SectionHeading
			align="center"
			eyebrow="Why NOVA Exists"
			title="A unified OS vs. a patchwork of foreign tools"
			subtitle="Most salons run on 4 disconnected systems that don't speak to each other. NOVA replaces the chaos with a single source of truth."
		/>

		<div class="mt-12 grid gap-6 md:grid-cols-2">
			<!-- Fragmented legacy box -->
			<div
				class="rounded-3xl border border-rose-200 bg-white p-6 shadow-sm sm:p-8 dark:border-rose-950/60 dark:bg-slate-900"
			>
				<div class="flex items-center gap-2 text-rose-600 dark:text-rose-400">
					<Icon name="x" class="size-5" />
					<h3 class="text-lg font-bold">The Fragmented Traditional Approach</h3>
				</div>
				<p class="mt-2 text-xs text-slate-500 dark:text-slate-400">
					How salons traditionally manage their front desk operations:
				</p>
				<ul class="mt-6 space-y-3.5">
					{#each comparisons as item (item.label)}
						<li
							class="rounded-xl border border-rose-100 bg-rose-50/60 p-3.5 dark:border-rose-900/40 dark:bg-rose-950/20"
						>
							<p
								class="text-xs font-bold tracking-wider text-rose-700 uppercase dark:text-rose-300"
							>
								{item.label}
							</p>
							<p class="mt-1 text-xs text-slate-700 dark:text-slate-300">{item.legacy}</p>
						</li>
					{/each}
				</ul>
			</div>

			<!-- NOVA unified box -->
			<div
				class="rounded-3xl border border-brand-300 bg-white p-6 shadow-md ring-2 ring-brand-500/20 sm:p-8 dark:border-brand-700 dark:bg-slate-900"
			>
				<div class="flex items-center gap-2 text-brand-600 dark:text-brand-400">
					<Icon name="check" class="size-5" />
					<h3 class="text-lg font-bold">The NOVA Unified Operating System</h3>
				</div>
				<p class="mt-2 text-xs text-slate-500 dark:text-slate-400">
					How a salon operates with NOVA:
				</p>
				<ul class="mt-6 space-y-3.5">
					{#each comparisons as item (item.label)}
						<li
							class="rounded-xl border border-brand-100 bg-brand-50/60 p-3.5 dark:border-brand-900/50 dark:bg-brand-950/30"
						>
							<p
								class="text-xs font-bold tracking-wider text-brand-700 uppercase dark:text-brand-300"
							>
								{item.label}
							</p>
							<p class="mt-1 text-xs text-slate-800 dark:text-slate-200">{item.nova}</p>
						</li>
					{/each}
				</ul>
			</div>
		</div>
	</Container>
</Section>

<!-- The 4 Core Architectural Commitments -->
<Section tone="canvas" class="py-16 sm:py-24">
	<Container size="xl">
		<SectionHeading
			align="center"
			eyebrow="Engineering Principles"
			title="Built on four non-negotiable foundations"
			subtitle="Every line of code and user experience decision is anchored in regional authenticity and computational rigor."
		/>

		<div class="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
			{#each pillars as pillar (pillar.title)}
				<div
					class="relative flex flex-col justify-between rounded-3xl border border-slate-200 bg-white p-6 shadow-xs transition-all hover:border-slate-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-900"
				>
					<div>
						<div
							class="inline-flex size-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-950/50 dark:text-brand-400"
						>
							<Icon name={pillar.icon} class="size-5" />
						</div>
						<h3 class="mt-4 text-base font-bold text-slate-900 dark:text-slate-100">
							{pillar.title}
						</h3>
						<p class="text-[11px] font-semibold text-brand-600 dark:text-brand-400">
							{pillar.subtitle}
						</p>
						<p class="mt-2.5 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
							{pillar.body}
						</p>
					</div>
				</div>
			{/each}
		</div>
	</Container>
</Section>

<!-- Privacy, Isolation, and PDPL Compliance -->
<Section tone="canvas" class="py-16 sm:py-24">
	<Container size="xl">
		<div class="grid items-center gap-10 lg:grid-cols-12">
			<div class="space-y-4 lg:col-span-6">
				<Badge tone="accent">Security &amp; privacy</Badge>
				<h2 class="text-display-md font-bold tracking-tight text-slate-900 dark:text-slate-100">
					Tenant isolation, built into the database
				</h2>
				<p class="text-xs leading-relaxed text-slate-600 dark:text-slate-400">
					Your client list, pricing and financial reports are confidential. Every query is scoped to
					the authenticated tenant at the database level, not just in application code.
				</p>
				<ul class="space-y-3 pt-2">
					<li class="flex items-start gap-3 text-xs text-slate-700 dark:text-slate-300">
						<Icon
							name="shield-check"
							class="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400"
						/>
						<span
							><strong>Row-level tenant isolation:</strong> Postgres enforces tenant boundaries with row-level
							security, not application code alone.</span
						>
					</li>
					<li class="flex items-start gap-3 text-xs text-slate-700 dark:text-slate-300">
						<Icon
							name="shield-check"
							class="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400"
						/>
						<span
							><strong>Cards handled by Moyasar:</strong> Card and Mada details are captured directly
							by Moyasar and never touch NOVA's servers.</span
						>
					</li>
					<li class="flex items-start gap-3 text-xs text-slate-700 dark:text-slate-300">
						<Icon
							name="shield-check"
							class="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400"
						/>
						<span
							><strong>Role-based staff access:</strong> A provider sees their own schedule; front-desk
							staff don't see owner-level financials.</span
						>
					</li>
				</ul>
			</div>
			<div class="lg:col-span-6">
				<div
					class="rounded-3xl border border-slate-200 bg-slate-50 p-8 dark:border-slate-800 dark:bg-slate-800/50"
				>
					<h3 class="text-base font-bold text-slate-900 dark:text-slate-100">
						Built with PDPL in mind
					</h3>
					<p class="mt-2 text-xs text-slate-600 dark:text-slate-400">
						Customer records carry explicit consent flags for marketing and communication,
						reflecting the Saudi Personal Data Protection Law's consent requirements.
					</p>
					<div class="mt-6 space-y-3">
						<div
							class="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-3.5 text-xs font-medium dark:border-slate-700 dark:bg-slate-900"
						>
							<span class="text-slate-700 dark:text-slate-300"
								>Tenant-scoped by row-level security</span
							>
							<span class="font-mono font-bold text-emerald-600">Enforced</span>
						</div>
						<div
							class="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-3.5 text-xs font-medium dark:border-slate-700 dark:bg-slate-900"
						>
							<span class="text-slate-700 dark:text-slate-300">Per-customer consent tracking</span>
							<span class="font-mono font-bold text-emerald-600">Built in</span>
						</div>
					</div>
				</div>
			</div>
		</div>
	</Container>
</Section>

<!-- Call to Action -->
<Section tone="dark" class="py-16 sm:py-24">
	<Container size="md" class="text-center">
		<h2 class="text-display-lg font-bold tracking-tight text-white">Bring your salon onto NOVA</h2>
		<p class="mt-4 text-body-lg text-white/80">
			Set up your storefront, services and providers in minutes.
		</p>
		<div class="mt-8 flex flex-wrap justify-center gap-3">
			<Button size="lg" variant="inverse" href={resolve('/register')}>
				Start 14-day free trial
			</Button>
			<Button size="lg" variant="outline-inverse" href={resolve('/discover')}>
				Find a salon near you
			</Button>
		</div>
	</Container>
</Section>
