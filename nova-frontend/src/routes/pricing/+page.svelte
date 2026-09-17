<script>
	import { resolve } from '$app/paths';
	import Container from '$lib/components/marketing/Container.svelte';
	import Section from '$lib/components/marketing/Section.svelte';
	import SectionHeading from '$lib/components/marketing/SectionHeading.svelte';
	import PricingTierCard from '$lib/components/marketing/PricingTierCard.svelte';

	// Illustrative pricing only — not wired to the billing API. The real plan/
	// subscription data (`$lib/api/billing.js`) is scoped to an authenticated
	// tenant and lives behind /app/billing; these tier names match the real
	// `PlanTier` values so marketing copy never contradicts the product.
	const tiers = [
		{
			name: 'Solo',
			priceMonthly: 149,
			description: 'One location, one provider.',
			features: [
				'Booking & walk-in queue',
				'WhatsApp confirmations & reminders',
				'Deposits via Moyasar',
				'Marketplace listing'
			]
		},
		{
			name: 'Studio',
			priceMonthly: 349,
			description: 'A small team, multiple providers.',
			features: [
				'Everything in Solo',
				'Multiple providers & schedules',
				'AI chat assistant for staff',
				'Analytics & reporting'
			],
			featured: true
		},
		{
			name: 'Chain',
			priceMonthly: 799,
			description: 'Multiple locations under one account.',
			features: [
				'Everything in Studio',
				'Multiple locations',
				'Role-based staff permissions',
				'Priority support'
			]
		}
	];

	const faqs = [
		{
			q: 'How does the marketplace commission work?',
			a: 'A booking that arrives through the NOVA marketplace carries a referral, and a small commission applies to that booking alongside your subscription. Bookings made directly on your own storefront link are not affected.'
		},
		{
			q: 'Can I change plans later?',
			a: 'Yes — your plan is tied to your business, not a contract term, and can move up or down as your team and locations change.'
		},
		{
			q: 'Do you take a cut of deposits?',
			a: 'No. Deposits and payments go through Moyasar under your own account; NOVA never holds customer funds.'
		},
		{
			q: 'Is there a setup fee?',
			a: 'No. Creating your storefront, services and providers is self-serve and included in every plan.'
		}
	];
</script>

<svelte:head><title>Pricing — NOVA</title></svelte:head>

<Section tone="canvas" padding="tight">
	<Container size="lg">
		<SectionHeading
			align="center"
			eyebrow="Pricing"
			title="Simple pricing, one commission model"
			subtitle="Billed monthly in SAR. No setup fee, no long-term contract."
		/>
	</Container>
</Section>

<Section tone="canvas" padding="none" class="pb-20 sm:pb-28">
	<Container size="lg">
		<div class="grid gap-8 lg:grid-cols-3">
			{#each tiers as tier (tier.name)}
				<PricingTierCard
					name={tier.name}
					priceMonthly={tier.priceMonthly}
					description={tier.description}
					features={tier.features}
					featured={tier.featured}
					ctaHref={resolve('/register')}
				/>
			{/each}
		</div>
	</Container>
</Section>

<Section tone="sunken">
	<Container size="md">
		<SectionHeading align="center" title="Questions" />
		<div class="mt-10 space-y-3">
			{#each faqs as item (item.q)}
				<details
					class="group rounded-xl border border-slate-200 bg-white p-5 open:shadow-sm dark:border-slate-800 dark:bg-slate-900"
				>
					<summary
						class="cursor-pointer list-none text-sm font-semibold text-slate-900 marker:content-none dark:text-slate-100"
					>
						{item.q}
					</summary>
					<p class="mt-3 text-sm text-slate-600 dark:text-slate-400">{item.a}</p>
				</details>
			{/each}
		</div>
	</Container>
</Section>
