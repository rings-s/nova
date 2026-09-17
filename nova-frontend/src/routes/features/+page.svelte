<script>
	import { resolve } from '$app/paths';
	import Button from '$lib/components/ui/Button.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import Section from '$lib/components/marketing/Section.svelte';
	import SectionHeading from '$lib/components/marketing/SectionHeading.svelte';
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';

	/** @type {{ icon: import('$lib/components/ui/Icon.svelte').IconName, title: string, body: string, points: string[] }[]} */
	const sections = [
		{
			icon: 'calendar',
			title: 'Booking & slot holds',
			body: 'Availability is computed live across every branch and provider — never a stale calendar. A slot is held the moment a customer starts checkout, so two people can never win the same appointment.',
			points: [
				'Per-provider schedules and skills',
				'Deterministic, real-time availability',
				'A short hold protects checkout'
			]
		},
		{
			icon: 'users',
			title: 'Walk-in queue',
			body: 'Walk-ins and appointments share one line instead of two systems that have to be reconciled by hand. A customer gets a ticket at the door and a live position in the queue.',
			points: [
				'One line for walk-ins and bookings',
				'Live queue position',
				'Call-next for the front desk'
			]
		},
		{
			icon: 'chat-bubble',
			title: 'WhatsApp messaging',
			body: 'Confirmations, reminders and receipts are sent on WhatsApp — the channel your customers already have open — not through a separate app they have to install.',
			points: [
				'Booking confirmations & reminders',
				'No new app for your customers',
				'Built into the booking flow itself'
			]
		},
		{
			icon: 'credit-card',
			title: 'Deposits & payments',
			body: 'Take a deposit to confirm a booking and cut down on no-shows. Card details are handled by Moyasar — NOVA never touches or stores a card number.',
			points: [
				'Configurable deposit percentage',
				'Moyasar handles card capture',
				'Clear payment status on every booking'
			]
		},
		{
			icon: 'globe',
			title: 'Marketplace discovery',
			body: 'A public, searchable marketplace lists every business that opts in, so customers who have never heard of you can find and book directly.',
			points: [
				'Search by city or service',
				'Public storefront per business',
				'Referral tracking on every booking'
			]
		},
		{
			icon: 'sparkles',
			title: 'AI chat assistant',
			body: 'A chat assistant your staff can ask about bookings, revenue and schedules. It only ever states numbers a real tool call returned — never a guess.',
			points: [
				'Grounded in your own data',
				'Staff-only, role-gated',
				'Proposes actions; your team confirms them'
			]
		},
		{
			icon: 'shield-check',
			title: 'Bilingual by design',
			body: 'Every business, service and provider name is stored in Arabic and English from the first record — not translated after the fact.',
			points: ['Arabic & English on every record', 'Built for the way the region actually works']
		}
	];
</script>

<svelte:head><title>Features — NOVA</title></svelte:head>

<Section tone="canvas" padding="tight">
	<GradientBlob variant="corner" />
	<Container size="lg">
		<SectionHeading
			align="center"
			eyebrow="Product"
			title="Everything your front desk needs"
			subtitle="Booking, walk-ins, messaging and payments — one platform instead of four."
		/>
	</Container>
</Section>

{#each sections as section, i (section.title)}
	<Section tone={i % 2 === 0 ? 'canvas' : 'sunken'}>
		<Container size="lg">
			<div class="grid items-center gap-12 lg:grid-cols-2">
				<div class={i % 2 === 1 ? 'lg:order-2' : ''}>
					<div
						class="inline-flex size-12 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-950/40 dark:text-brand-400"
					>
						<Icon name={section.icon} class="size-6" />
					</div>
					<h2
						class="mt-5 text-display-md font-semibold tracking-tight text-slate-900 dark:text-slate-100"
					>
						{section.title}
					</h2>
					<p class="mt-4 text-body-lg text-slate-600 dark:text-slate-400">{section.body}</p>
					<ul class="mt-6 space-y-2">
						{#each section.points as point (point)}
							<li class="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-300">
								<Icon
									name="check"
									class="mt-0.5 size-4 shrink-0 text-brand-600 dark:text-brand-400"
								/>
								<span>{point}</span>
							</li>
						{/each}
					</ul>
				</div>
				<div class={['relative', i % 2 === 1 ? 'lg:order-1' : ''].join(' ')} aria-hidden="true">
					<div
						class="flex aspect-4/3 items-center justify-center rounded-3xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900"
					>
						<Icon name={section.icon} class="size-24 text-brand-100 dark:text-brand-950" />
					</div>
				</div>
			</div>
		</Container>
	</Section>
{/each}

<Section tone="dark">
	<Container size="md" class="text-center">
		<h2 class="text-display-lg font-semibold tracking-tight">
			See it running on your own storefront
		</h2>
		<p class="mt-4 text-body-lg text-white/80">Set up takes minutes — no credit card required.</p>
		<div class="mt-8 flex justify-center">
			<Button size="lg" variant="inverse" href={resolve('/register')}>Get started</Button>
		</div>
	</Container>
</Section>
