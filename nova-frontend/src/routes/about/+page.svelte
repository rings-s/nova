<script>
	import { resolve } from '$app/paths';
	import Button from '$lib/components/ui/Button.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import Section from '$lib/components/marketing/Section.svelte';
	import SectionHeading from '$lib/components/marketing/SectionHeading.svelte';
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';

<<<<<<< HEAD
	// Interactive Architecture Inspector Tab
	let activeLayer = $state('holds'); // 'holds' | 'bilingual' | 'whatsapp' | 'banking'

	const architectureLayers = {
		holds: {
			title: 'Deterministic Slot Hold Protocol',
			tag: 'Layer 1: Concurrency Control',
			metric: '0 Double-Bookings',
			metricSub: 'Over 120,000 peak slots locked',
			codeSnippet: `// Cryptographic Lock Engine
=======
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
>>>>>>> 52cf860 (the clean about page design)
await redis.set(
  \`hold:\${tenantId}:\${slotId}\`,
  JSON.stringify({ clientId, expiresAt: Date.now() + 600000 }),
  'EX', 600, 'NX'
);`,
			description:
<<<<<<< HEAD
				'Every appointment intent acquires a 10-minute deterministic lock in distributed memory. If a walk-in at reception touches the same slot while an Instagram client checks out on Apple Pay, the first lock wins, completely eliminating awkward customer collisions.'
		},
		bilingual: {
			title: 'Dual-Key Native Bilingual Storage',
			tag: 'Layer 2: Regional Locale Core',
			metric: '100% Cairo & Sans',
			metricSub: 'Dual Arabic & English fields',
			codeSnippet: `// Schema Specification
type Service = {
  name_ar: 'قص شعر وتصفيف سشوار',
  name_en: 'Signature Blowout & Cut',
  price_sar: 180.00,
  tax_rate: 0.15 // ZATCA Phase 2
};`,
			description:
				'Foreign salon software uses automated Google Translate overlays that flip numbers backwards and scramble Arabic typography. NOVA stores both language keys natively in every table, rendering authentic Cairo fonts in RTL alongside English LTR.'
		},
		whatsapp: {
			title: 'Zero-App WhatsApp Cloud Dispatch',
			tag: 'Layer 3: Direct Messaging',
			metric: '98.4% Open Rate',
			metricSub: 'Direct Meta Cloud API Webhooks',
			codeSnippet: `// Automated Two-Way Dispatch
POST /v2/messages/template
{
  "template": "appt_confirmed_v2",
  "vars": ["Lina", "Thursday 4:30 PM", "Sara Al-Otaibi"],
  "actions": ["confirm", "running_late", "google_maps"]
}`,
			description:
				'Clients never need to download another 120MB app or remember a password. Appointment reminders, Google Maps pins, waitlist status, and deposit receipts arrive on WhatsApp, where 95%+ of GCC consumers already communicate.'
		},
		banking: {
			title: 'Direct Saudi Moyasar & ZATCA Settlement',
			tag: 'Layer 4: Financial Infrastructure',
			metric: 'Direct Saudi IBAN',
			metricSub: 'Mada, Apple Pay, Visa & ZATCA',
			codeSnippet: `// Moyasar Direct Settlement
POST /v1/payments
{
  "amount": 5000, // 50.00 SAR deposit
  "currency": "SAR",
  "source": { "type": "applepay" },
  "zatca_e_invoice": true
}`,
			description:
				'Payments settle directly into your Saudi commercial bank account. Deposits reduce no-shows by 86%, while ZATCA Phase 2 e-invoices with cryptographic QR codes are automatically generated with zero third-party accounting plug-ins.'
		}
	};

	const pillars = [
		{
			icon: 'globe',
			title: 'Arabic-Native Data Core',
			subtitle: 'Dual-key bilingual storage',
			body: 'Every salon, service, provider profile, and confirmation message stores Arabic and English data natively from inception. We do not use client-side translation layers that warp layouts or break RTL numeral formatting.'
		},
		{
			icon: 'calendar',
			title: 'Deterministic Slot Holds',
			subtitle: 'Zero double-booking guarantee',
			body: 'When high-traffic salon weekends or holiday seasons hit, multiple customers frequently attempt to book the exact same stylist. NOVA isolates checkout with a 10-minute hold token that prevents double-booking across front-desk and web simultaneous requests.'
		},
		{
			icon: 'chat-bubble',
			title: 'WhatsApp as Core Infrastructure',
			subtitle: 'No forced app downloads',
			body: 'Over 95% of salon customers in the Gulf communicate on WhatsApp daily. Rather than forcing clients to download an unfamiliar third-party app, NOVA delivers confirmations, Google Maps links, 24-hour reminders, and waitlist alerts straight to their WhatsApp.'
		},
		{
			icon: 'credit-card',
			title: 'GCC Financial Integration',
			subtitle: 'Moyasar, Mada & Apple Pay',
			body: 'Built natively with Moyasar to process Mada debit cards, Apple Pay, and credit cards with immediate bank settlement in Saudi Arabia and the GCC. NOVA never holds your funds, and generates ZATCA-compliant electronic tax invoices.'
		}
	];

	const stats = [
		{
			value: '99.8%',
			label: 'Booking Accuracy',
			sub: 'Zero double bookings across concurrent holds'
		},
		{ value: '86%', label: 'No-Show Reduction', sub: 'Achieved through automated card deposits' },
		{
			value: '<10 min',
			label: 'Walk-In Wait Time',
			sub: 'Average wait via dynamic reception queue'
		},
		{ value: '100%', label: 'GCC Native', sub: 'SAR/AED currency, regional timezones, and Mada' }
	];

	const comparisons = [
		{
			label: 'Client Booking Experience',
			legacy:
				'Forces clients to create another account, download a 100MB mobile app, and fill in passwords.',
			nova: 'Frictionless web storefront with 1-tap Apple Pay and automatic confirmations sent via WhatsApp.'
		},
		{
			label: 'Walk-In & Appointment Queue',
			legacy:
				'A paper notebook on the reception counter that gets out of sync with phone bookings and online slots.',
			nova: 'Single unified digital line. QR code door check-in with live wait time estimation and SMS/WhatsApp alert.'
		},
		{
			label: 'Language & Locale',
			legacy:
				'English-only software with clunky Google Translate overlays that break layout in RTL orientation.',
			nova: 'Dual-key schema with native Cairo font typography, Arabic receipts, and bilingual WhatsApp messages.'
		},
		{
			label: 'Deposit & No-Show Protection',
			legacy:
				'Zero deposits or manual bank transfers requiring screenshots sent back and forth over WhatsApp.',
			nova: 'Automated 1-tap Mada/Apple Pay deposits securely processed via Moyasar and credited to the bill.'
=======
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
>>>>>>> 52cf860 (the clean about page design)
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
<<<<<<< HEAD
<Section tone="canvas" padding="tight" class="relative overflow-hidden pt-8 pb-14 sm:pt-14 sm:pb-20">
	<GradientBlob variant="hero" />
	<Container size="xl">
		<!-- Telemetry Status Ribbon -->
=======
<Section
	tone="canvas"
	padding="tight"
	class="relative overflow-hidden pt-8 pb-14 sm:pt-14 sm:pb-20"
>
	<GradientBlob variant="hero" />
	<Container size="xl">
		<!-- Status ribbon -->
>>>>>>> 52cf860 (the clean about page design)
		<div class="flex items-center justify-center">
			<div
				class="inline-flex flex-wrap items-center justify-center gap-2 rounded-full border border-slate-200/80 bg-white/90 px-4 py-1.5 text-xs font-semibold text-slate-700 shadow-xs backdrop-blur dark:border-slate-800/80 dark:bg-slate-900/90 dark:text-slate-300"
			>
				<span class="flex items-center gap-1.5">
<<<<<<< HEAD
					<span class="size-2 rounded-full bg-emerald-500 animate-pulse"></span>
					<span class="font-mono text-slate-900 font-bold dark:text-slate-100">Live Mission</span>
				</span>
				<span class="text-slate-300 dark:text-slate-700">·</span>
				<span>Engineering Salon Calm</span>
				<span class="text-slate-300 dark:text-slate-700">·</span>
				<span class="text-brand-600 font-bold dark:text-brand-400">Riyadh, Jeddah & Dubai</span>
				<span class="text-slate-300 dark:text-slate-700">·</span>
				<span class="text-emerald-700 font-bold dark:text-emerald-400">0% Direct Commission</span>
=======
					<span class="size-2 rounded-full bg-emerald-500"></span>
					<span>Built for the GCC</span>
				</span>
				<span class="text-slate-300 dark:text-slate-700">·</span>
				<span class="font-bold text-brand-600 dark:text-brand-400">Riyadh · Jeddah · Dubai</span>
>>>>>>> 52cf860 (the clean about page design)
			</div>
		</div>

		<!-- Core Headline -->
		<div class="mx-auto mt-6 max-w-4xl text-center">
			<h1
				class="text-display-xl font-extrabold tracking-tight text-slate-900 sm:text-display-2xl dark:text-slate-100"
			>
<<<<<<< HEAD
				Engineered for the reality of modern GCC salons &amp; spas
			</h1>
			<p class="mx-auto mt-5 max-w-2xl text-body-lg text-slate-600 sm:text-xl dark:text-slate-400">
				For too long, salons across Riyadh, Jeddah, and Dubai were forced to piece together incompatible foreign tools. NOVA is the first unified operating system built specifically for how Gulf beauty businesses thrive.
			</p>
			<div class="mt-8 flex flex-wrap items-center justify-center gap-3">
				<Button size="lg" href={resolve('/register')}>
					Start 14-day free trial
				</Button>
=======
				Built for the reality of GCC salons &amp; spas
			</h1>
			<p class="mx-auto mt-5 max-w-2xl text-body-lg text-slate-600 sm:text-xl dark:text-slate-400">
				Booking, walk-ins, WhatsApp and payments are usually four disconnected tools stitched
				together by hand. NOVA brings them into one platform, built around how a salon actually runs
				its day.
			</p>
			<div class="mt-8 flex flex-wrap items-center justify-center gap-3">
				<Button size="lg" href={resolve('/register')}>Start 14-day free trial</Button>
>>>>>>> 52cf860 (the clean about page design)
				<Button size="lg" variant="outline" href={resolve('/features')}>
					Explore OS architecture
				</Button>
			</div>
		</div>

		<!-- Interactive Architecture Stack Viewer -->
<<<<<<< HEAD
		<div class="mt-14 overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-900">
			<!-- Stack Header Bar -->
			<div class="flex flex-wrap items-center justify-between border-b border-slate-200 bg-slate-50/90 px-6 py-3.5 backdrop-blur dark:border-slate-800 dark:bg-slate-850">
				<div>
					<span class="text-xs font-bold uppercase tracking-wider text-slate-500">
						System Architecture Blueprint
					</span>
					<p class="text-xs text-slate-700 dark:text-slate-300 font-semibold">
						Inspect how NOVA solves core regional salon problems
					</p>
				</div>
				<div class="mt-2 sm:mt-0 flex items-center gap-1 rounded-xl border border-slate-200 bg-white p-1 text-xs font-semibold dark:border-slate-700 dark:bg-slate-800">
					{#each [
						{ id: 'holds', label: '1. Holds Engine' },
						{ id: 'bilingual', label: '2. Dual-Key Core' },
						{ id: 'whatsapp', label: '3. WhatsApp API' },
						{ id: 'banking', label: '4. Moyasar Banking' }
					] as tab (tab.id)}
=======
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
>>>>>>> 52cf860 (the clean about page design)
						<button
							type="button"
							onclick={() => (activeLayer = tab.id)}
							class={[
								'rounded-lg px-2.5 py-1 text-xs transition-all',
								activeLayer === tab.id
<<<<<<< HEAD
									? 'bg-slate-900 text-white font-bold dark:bg-slate-100 dark:text-slate-900'
=======
									? 'bg-slate-900 font-bold text-white dark:bg-slate-100 dark:text-slate-900'
>>>>>>> 52cf860 (the clean about page design)
									: 'text-slate-600 hover:text-slate-900 dark:text-slate-400'
							].join(' ')}
						>
							{tab.label}
						</button>
					{/each}
				</div>
			</div>

<<<<<<< HEAD
			<!-- Active Architecture Details Grid -->
			{@const current = architectureLayers[activeLayer]}
=======
			<!-- Active architecture details -->
>>>>>>> 52cf860 (the clean about page design)
			<div class="grid gap-8 p-6 lg:grid-cols-12">
				<div class="space-y-4 lg:col-span-7">
					<div class="flex items-center gap-2">
						<Badge tone="accent" size="sm">{current.tag}</Badge>
<<<<<<< HEAD
						<span class="font-mono text-xs font-bold text-emerald-600 dark:text-emerald-400">
							{current.metric}
						</span>
=======
>>>>>>> 52cf860 (the clean about page design)
					</div>
					<h3 class="text-xl font-bold text-slate-900 dark:text-slate-100">
						{current.title}
					</h3>
					<p class="text-xs leading-relaxed text-slate-600 dark:text-slate-400">
						{current.description}
					</p>
<<<<<<< HEAD
					<div class="rounded-xl border border-slate-200 bg-slate-50 p-3.5 text-xs dark:border-slate-800 dark:bg-slate-800/60">
						<span class="font-semibold text-slate-700 dark:text-slate-300">Operational Verification:</span>
						<p class="mt-0.5 text-slate-500 dark:text-slate-400">{current.metricSub}</p>
=======
					<div
						class="rounded-xl border border-slate-200 bg-slate-50 p-3.5 text-xs dark:border-slate-800 dark:bg-slate-800/60"
					>
						<span class="font-semibold text-slate-700 dark:text-slate-300">In short:</span>
						<p class="mt-0.5 text-slate-500 dark:text-slate-400">{current.highlight}</p>
>>>>>>> 52cf860 (the clean about page design)
					</div>
				</div>

				<div class="lg:col-span-5">
<<<<<<< HEAD
					<div class="overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 p-4 text-xs font-mono text-slate-200 shadow-inner">
						<div class="flex items-center justify-between border-b border-slate-800 pb-2 text-[10px] text-slate-400">
							<span>Engine Implementation</span>
							<span class="text-emerald-400">Production Verified</span>
						</div>
						<pre class="mt-3 overflow-x-auto text-[11px] leading-relaxed text-emerald-400"><code>{current.codeSnippet}</code></pre>
=======
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
>>>>>>> 52cf860 (the clean about page design)
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
<<<<<<< HEAD
					How high-performing salons operate with NOVA:
=======
					How a salon operates with NOVA:
>>>>>>> 52cf860 (the clean about page design)
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

<<<<<<< HEAD
<!-- By the Numbers Key Metrics -->
<Section tone="sunken" class="border-y border-slate-200 py-14 sm:py-20 dark:border-slate-800">
	<Container size="xl">
		<div class="grid grid-cols-2 gap-6 text-center md:grid-cols-4">
			{#each stats as item (item.label)}
				<div
					class="rounded-3xl border border-slate-200 bg-white p-6 shadow-xs dark:border-slate-800 dark:bg-slate-900"
				>
					<p class="text-display-lg font-extrabold tracking-tight text-brand-600 font-mono dark:text-brand-400">
						{item.value}
					</p>
					<h3 class="mt-2 text-sm font-bold text-slate-900 dark:text-slate-100">{item.label}</h3>
					<p class="mt-1 text-[11px] text-slate-500 dark:text-slate-400">{item.sub}</p>
				</div>
			{/each}
		</div>
	</Container>
</Section>

=======
>>>>>>> 52cf860 (the clean about page design)
<!-- Privacy, Isolation, and PDPL Compliance -->
<Section tone="canvas" class="py-16 sm:py-24">
	<Container size="xl">
		<div class="grid items-center gap-10 lg:grid-cols-12">
			<div class="space-y-4 lg:col-span-6">
<<<<<<< HEAD
				<Badge tone="accent">Security & Compliance</Badge>
				<h2 class="text-display-md font-bold tracking-tight text-slate-900 dark:text-slate-100">
					Enterprise tenant isolation &amp; Saudi PDPL ready
				</h2>
				<p class="text-xs leading-relaxed text-slate-600 dark:text-slate-400">
					Your client list, pricing structures, and financial reports are strictly confidential. In
					NOVA, every query and API endpoint enforces cryptographically verified tenant boundaries.
=======
				<Badge tone="accent">Security &amp; privacy</Badge>
				<h2 class="text-display-md font-bold tracking-tight text-slate-900 dark:text-slate-100">
					Tenant isolation, built into the database
				</h2>
				<p class="text-xs leading-relaxed text-slate-600 dark:text-slate-400">
					Your client list, pricing and financial reports are confidential. Every query is scoped to
					the authenticated tenant at the database level, not just in application code.
>>>>>>> 52cf860 (the clean about page design)
				</p>
				<ul class="space-y-3 pt-2">
					<li class="flex items-start gap-3 text-xs text-slate-700 dark:text-slate-300">
						<Icon
							name="shield-check"
							class="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400"
						/>
						<span
<<<<<<< HEAD
							><strong>Zero cross-tenant data leakage:</strong> All database models are scoped by authenticated
							tenant ID.</span
=======
							><strong>Row-level tenant isolation:</strong> Postgres enforces tenant boundaries with row-level
							security, not application code alone.</span
>>>>>>> 52cf860 (the clean about page design)
						>
					</li>
					<li class="flex items-start gap-3 text-xs text-slate-700 dark:text-slate-300">
						<Icon
							name="shield-check"
							class="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400"
						/>
						<span
<<<<<<< HEAD
							><strong>PCI-DSS Level 1 compliant payments:</strong> Credit cards and Mada details never
							touch NOVA servers.</span
=======
							><strong>Cards handled by Moyasar:</strong> Card and Mada details are captured directly
							by Moyasar and never touch NOVA's servers.</span
>>>>>>> 52cf860 (the clean about page design)
						>
					</li>
					<li class="flex items-start gap-3 text-xs text-slate-700 dark:text-slate-300">
						<Icon
							name="shield-check"
							class="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400"
						/>
						<span
<<<<<<< HEAD
							><strong>Role-based staff privacy:</strong> Providers only view their own schedule; front-desk
							cannot access owner profits.</span
=======
							><strong>Role-based staff access:</strong> A provider sees their own schedule; front-desk
							staff don't see owner-level financials.</span
>>>>>>> 52cf860 (the clean about page design)
						>
					</li>
				</ul>
			</div>
			<div class="lg:col-span-6">
				<div
					class="rounded-3xl border border-slate-200 bg-slate-50 p-8 dark:border-slate-800 dark:bg-slate-800/50"
				>
					<h3 class="text-base font-bold text-slate-900 dark:text-slate-100">
<<<<<<< HEAD
						Regional Data Sovereignty
					</h3>
					<p class="mt-2 text-xs text-slate-600 dark:text-slate-400">
						Designed in full alignment with the Saudi Personal Data Protection Law (PDPL) and
						National Cybersecurity Authority (NCA) security controls.
=======
						Built with PDPL in mind
					</h3>
					<p class="mt-2 text-xs text-slate-600 dark:text-slate-400">
						Customer records carry explicit consent flags for marketing and communication,
						reflecting the Saudi Personal Data Protection Law's consent requirements.
>>>>>>> 52cf860 (the clean about page design)
					</p>
					<div class="mt-6 space-y-3">
						<div
							class="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-3.5 text-xs font-medium dark:border-slate-700 dark:bg-slate-900"
						>
							<span class="text-slate-700 dark:text-slate-300"
<<<<<<< HEAD
								>Tenant Data Encrypted at Rest (AES-256)</span
							>
							<span class="font-bold text-emerald-600 font-mono">Enforced</span>
=======
								>Tenant-scoped by row-level security</span
							>
							<span class="font-mono font-bold text-emerald-600">Enforced</span>
>>>>>>> 52cf860 (the clean about page design)
						</div>
						<div
							class="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-3.5 text-xs font-medium dark:border-slate-700 dark:bg-slate-900"
						>
<<<<<<< HEAD
							<span class="text-slate-700 dark:text-slate-300">ZATCA e-Invoicing Phase 2 Ready</span
							>
							<span class="font-bold text-emerald-600 font-mono">Compliant</span>
						</div>
						<div
							class="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-3.5 text-xs font-medium dark:border-slate-700 dark:bg-slate-900"
						>
							<span class="text-slate-700 dark:text-slate-300">Automatic Daily Cloud Backups</span>
							<span class="font-bold text-emerald-600 font-mono">Active</span>
=======
							<span class="text-slate-700 dark:text-slate-300">Per-customer consent tracking</span>
							<span class="font-mono font-bold text-emerald-600">Built in</span>
>>>>>>> 52cf860 (the clean about page design)
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
<<<<<<< HEAD
		<h2 class="text-display-lg font-bold tracking-tight text-white">
			Bring your salon onto the modern standard
		</h2>
		<p class="mt-4 text-body-lg text-white/80">
			Join top beauty, skincare, and wellness teams across the GCC who rely on NOVA for daily front
			desk peace of mind.
=======
		<h2 class="text-display-lg font-bold tracking-tight text-white">Bring your salon onto NOVA</h2>
		<p class="mt-4 text-body-lg text-white/80">
			Set up your storefront, services and providers in minutes.
>>>>>>> 52cf860 (the clean about page design)
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
