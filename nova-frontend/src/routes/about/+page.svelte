<script>
	import { resolve } from '$app/paths';
	import Tabs from '$lib/components/ui/Tabs.svelte';
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
		{ id: 'holds', label: 'Slot holds' },
		{ id: 'bilingual', label: 'Bilingual data' },
		{ id: 'whatsapp', label: 'WhatsApp' },
		{ id: 'banking', label: 'Payments' }
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
	<title>About — NOVA</title>
	<meta
		name="description"
		content="Learn about NOVA's mission: replacing fragmented salon software with a unified, bilingual operating system engineered for Saudi Arabia and the GCC."
	/>
</svelte:head>

<!-- Master Hero Header -->
<Section tone="canvas">
	<GradientBlob variant="hero" />
	<Container size="xl">
		<!-- Status ribbon -->
		<div class="flex items-center justify-center">
			<p
				class="inline-flex items-center gap-2 rounded-full border border-line bg-surface/80 px-3 py-1 text-xs font-medium text-fg-secondary backdrop-blur"
			>
				<span class="size-1.5 rounded-full bg-brand-500"></span>
				Built for the GCC · Riyadh, Jeddah, Dubai
			</p>
		</div>

		<!-- Core Headline -->
		<div class="mx-auto mt-6 max-w-4xl text-center">
			<h1 class="text-display-2xl font-semibold tracking-tight text-fg">
				Built for the reality of GCC salons &amp; spas
			</h1>
			<p class="mx-auto mt-6 max-w-2xl text-body-lg text-fg-muted">
				Booking, walk-ins, WhatsApp and payments are usually four disconnected tools stitched
				together by hand. NOVA brings them into one platform, built around how a salon actually runs
				its day.
			</p>
			<div class="mt-8 flex flex-wrap items-center justify-center gap-3">
				<Button size="lg" href={`${resolve('/register')}?as=business`}
					>Start 14-day free trial</Button
				>
				<Button size="lg" variant="outline" href={resolve('/features')}>Explore features</Button>
			</div>
		</div>

		<!-- Interactive Architecture Stack Viewer -->
		<div class="mt-16 overflow-hidden rounded-panel border border-line bg-surface shadow-overlay">
			<!-- Stack Header Bar -->
			<div
				class="flex flex-wrap items-center justify-between gap-4 border-b border-line bg-surface-sunken px-6 py-4"
			>
				<div>
					<p class="text-xs font-semibold tracking-wider text-fg-subtle uppercase">
						Under the hood
					</p>
					<p class="text-sm font-medium text-fg">
						How NOVA solves the problems salons actually have
					</p>
				</div>
				<Tabs tabs={layerTabs} bind:active={activeLayer} />
			</div>

			<!-- Active architecture details -->
			<div class="grid gap-8 p-6 lg:grid-cols-12">
				<div class="space-y-4 lg:col-span-7">
					<div class="flex items-center gap-2">
						<Badge tone="accent" size="sm">{current.tag}</Badge>
					</div>
					<h3 class="text-xl font-semibold tracking-tight text-fg">
						{current.title}
					</h3>
					<p class="text-sm leading-relaxed text-fg-muted">
						{current.description}
					</p>
					<div class="rounded-card border border-line bg-surface-sunken p-4 text-sm">
						<span class="font-semibold text-fg">In short</span>
						<p class="mt-1 text-fg-muted">{current.highlight}</p>
					</div>
				</div>

				<div class="lg:col-span-5">
					<div
						class="overflow-hidden rounded-card border border-slate-800 bg-slate-950 p-4 font-mono text-xs text-slate-200"
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
<Section tone="sunken" class="border-y border-line">
	<Container size="xl">
		<SectionHeading
			align="center"
			eyebrow="Why NOVA exists"
			title="A unified OS vs. a patchwork of foreign tools"
			subtitle="Most salons run on 4 disconnected systems that don't speak to each other. NOVA replaces the chaos with a single source of truth."
		/>

		<div class="mt-12 grid gap-6 md:grid-cols-2">
			<!-- Fragmented legacy box -->
			<div class="rounded-panel border border-line bg-surface p-6 shadow-card sm:p-8">
				<div class="flex items-center gap-3">
					<span
						class="flex size-8 items-center justify-center rounded-full bg-surface-muted text-fg-muted"
					>
						<Icon name="x" class="size-4" />
					</span>
					<h3 class="text-lg font-semibold text-fg">The patchwork way</h3>
				</div>
				<p class="mt-3 text-sm text-fg-muted">
					How salons traditionally manage their front desk operations:
				</p>
				<ul class="mt-6 space-y-3.5">
					{#each comparisons as item (item.label)}
						<li class="rounded-card border border-line bg-surface-sunken p-4">
							<p class="text-xs font-semibold tracking-wider text-fg-subtle uppercase">
								{item.label}
							</p>
							<p class="mt-1 text-sm text-fg-muted">{item.legacy}</p>
						</li>
					{/each}
				</ul>
			</div>

			<!-- NOVA unified box -->
			<div
				class="rounded-panel border border-brand-300 bg-surface p-6 shadow-raised ring-4 ring-brand-500/10 sm:p-8 dark:border-brand-500/40"
			>
				<div class="flex items-center gap-3">
					<span
						class="flex size-8 items-center justify-center rounded-full bg-brand-600 text-white"
					>
						<Icon name="check" class="size-4" />
					</span>
					<h3 class="text-lg font-semibold text-fg">The NOVA way</h3>
				</div>
				<p class="mt-3 text-sm text-fg-muted">How a salon operates with NOVA:</p>
				<ul class="mt-6 space-y-3.5">
					{#each comparisons as item (item.label)}
						<li
							class="rounded-card border border-brand-100 bg-accent-soft/60 p-4 dark:border-brand-500/20"
						>
							<p class="text-xs font-semibold tracking-wider text-accent uppercase">
								{item.label}
							</p>
							<p class="mt-1 text-sm text-fg">{item.nova}</p>
						</li>
					{/each}
				</ul>
			</div>
		</div>
	</Container>
</Section>

<!-- The 4 Core Architectural Commitments -->
<Section tone="canvas">
	<Container size="xl">
		<SectionHeading
			align="center"
			eyebrow="Engineering principles"
			title="Built on four non-negotiable foundations"
			subtitle="Every line of code and user experience decision is anchored in regional authenticity and computational rigor."
		/>

		<div class="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
			{#each pillars as pillar (pillar.title)}
				<div
					class="relative flex flex-col rounded-card border border-line bg-surface p-6 shadow-card transition-[border-color,box-shadow,transform] duration-base ease-out-premium hover:-translate-y-0.5 hover:border-line-strong hover:shadow-raised"
				>
					<div>
						<div
							class="inline-flex size-11 items-center justify-center rounded-control bg-accent-soft text-accent"
						>
							<Icon name={pillar.icon} class="size-5" />
						</div>
						<h3 class="mt-4 text-base font-semibold text-fg">
							{pillar.title}
						</h3>
						<p class="text-xs font-medium text-accent">
							{pillar.subtitle}
						</p>
						<p class="mt-3 text-sm leading-relaxed text-fg-muted">
							{pillar.body}
						</p>
					</div>
				</div>
			{/each}
		</div>
	</Container>
</Section>

<!-- Privacy, Isolation, and PDPL Compliance -->
<Section tone="canvas">
	<Container size="xl">
		<div class="grid items-center gap-10 lg:grid-cols-12">
			<div class="space-y-4 lg:col-span-6">
				<Badge tone="accent">Security &amp; privacy</Badge>
				<h2 class="text-display-md font-semibold tracking-tight text-fg">
					Tenant isolation, built into the database
				</h2>
				<p class="text-body-lg text-fg-muted">
					Your client list, pricing and financial reports are confidential. Every query is scoped to
					the authenticated tenant at the database level, not just in application code.
				</p>
				<ul class="space-y-3 pt-2">
					<li class="flex items-start gap-3 text-sm text-fg-secondary">
						<Icon
							name="shield-check"
							class="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400"
						/>
						<span
							><strong>Row-level tenant isolation:</strong> Postgres enforces tenant boundaries with row-level
							security, not application code alone.</span
						>
					</li>
					<li class="flex items-start gap-3 text-sm text-fg-secondary">
						<Icon
							name="shield-check"
							class="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400"
						/>
						<span
							><strong>Cards handled by Moyasar:</strong> Card and Mada details are captured directly
							by Moyasar and never touch NOVA's servers.</span
						>
					</li>
					<li class="flex items-start gap-3 text-sm text-fg-secondary">
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
				<div class="rounded-panel border border-line bg-surface-sunken p-8">
					<h3 class="text-base font-semibold text-fg">Built with PDPL in mind</h3>
					<p class="mt-2 text-sm text-fg-muted">
						Customer records carry explicit consent flags for marketing and communication,
						reflecting the Saudi Personal Data Protection Law's consent requirements.
					</p>
					<div class="mt-6 space-y-3">
						<div
							class="flex items-center justify-between rounded-card border border-line bg-surface p-4 text-sm font-medium shadow-card"
						>
							<span class="text-fg-secondary">Tenant-scoped by row-level security</span>
							<span class="font-semibold text-emerald-600 dark:text-emerald-400">Enforced</span>
						</div>
						<div
							class="flex items-center justify-between rounded-card border border-line bg-surface p-4 text-sm font-medium shadow-card"
						>
							<span class="text-fg-secondary">Per-customer consent tracking</span>
							<span class="font-semibold text-emerald-600 dark:text-emerald-400">Built in</span>
						</div>
					</div>
				</div>
			</div>
		</div>
	</Container>
</Section>

<!-- Call to Action -->
<Section
	tone="dark"
	padding="tight"
	class="mx-4 mb-16 rounded-panel sm:mx-6 lg:mx-auto lg:max-w-7xl"
>
	<GradientBlob variant="corner" />
	<Container size="md" class="relative py-8 text-center sm:py-12">
		<h2 class="text-display-lg font-semibold tracking-tight text-white">
			Bring your salon onto NOVA
		</h2>
		<p class="mt-4 text-body-lg text-white/80">
			Set up your storefront, services and providers in minutes.
		</p>
		<div class="mt-8 flex flex-wrap justify-center gap-3">
			<Button size="lg" variant="inverse" href={`${resolve('/register')}?as=business`}>
				Start 14-day free trial
			</Button>
			<Button size="lg" variant="outline-inverse" href={resolve('/discover')}>
				Find a salon near you
			</Button>
		</div>
	</Container>
</Section>
