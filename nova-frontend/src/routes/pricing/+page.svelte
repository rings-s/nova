
<script>
	import { resolve } from '$app/paths';
	import Button from '$lib/components/ui/Button.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import Section from '$lib/components/marketing/Section.svelte';
	import SectionHeading from '$lib/components/marketing/SectionHeading.svelte';
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';

	// Illustrative pricing only — not wired to the billing API.
	// These names match the real PlanTier values.
	const tiers = [
		{
			name: 'Solo',
			priceMonthly: 149,
			description: 'One location, one provider.',
			label: 'For independent operators',
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
			label: 'For growing teams',
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
			label: 'For multi-location businesses',
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
			a: 'A booking that arrives through the NOVA marketplace carries a referral, and a small commission applies to that booking alongside your subscription. Bookings made directly through your own storefront are not affected.'
		},
		{
			q: 'Can I change plans later?',
			a: 'Yes. Your plan is tied to your business rather than a long-term contract, so you can move up or down as your team and locations change.'
		},
		{
			q: 'Do you take a cut of deposits?',
			a: 'No. Deposits and payments go through Moyasar under your own account. NOVA does not hold customer funds.'
		},
		{
			q: 'Is there a setup fee?',
			a: 'No. Creating your storefront, services and providers is self-serve and included with every plan.'
		}
	];
</script>

<svelte:head>
	<title>Pricing — NOVA</title>
	<meta
		name="description"
		content="Simple monthly pricing for NOVA's booking, queue, payments and business management platform."
	/>
</svelte:head>

<!-- ========================================================= -->
<!-- HERO -->
<!-- ========================================================= -->

<Section
	tone="canvas"
	padding="tight"
	class="relative overflow-hidden pt-8 pb-14 sm:pt-14 sm:pb-20"
>
	<GradientBlob variant="hero" />

	<Container size="xl">
		<div class="mx-auto max-w-4xl text-center">
			<div
				class="inline-flex items-center gap-2 rounded-full border border-slate-200/80 bg-white/90 px-4 py-1.5 text-xs font-semibold text-slate-700 shadow-xs backdrop-blur dark:border-slate-800/80 dark:bg-slate-900/90 dark:text-slate-300"
			>
				<span class="size-2 rounded-full bg-emerald-500"></span>
				<span>Simple monthly pricing</span>
			</div>

			<h1
				class="mt-6 text-display-xl font-extrabold tracking-tight text-slate-900 sm:text-display-2xl dark:text-slate-100"
			>
				Choose the plan that fits
				<span class="text-brand-600 dark:text-brand-400">your business.</span>
			</h1>

			<p
				class="mx-auto mt-5 max-w-2xl text-body-lg text-slate-600 sm:text-xl dark:text-slate-400"
			>
				Every plan includes the core NOVA operating system. Start small and expand
				as your team and locations grow.
			</p>

			<div class="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs font-medium text-slate-500 dark:text-slate-400">
				<span class="flex items-center gap-1.5">
					<Icon name="check" class="size-3.5 text-emerald-500" />
					Billed monthly in SAR
				</span>

				<span class="flex items-center gap-1.5">
					<Icon name="check" class="size-3.5 text-emerald-500" />
					No setup fee
				</span>

				<span class="flex items-center gap-1.5">
					<Icon name="check" class="size-3.5 text-emerald-500" />
					No long-term contract
				</span>
			</div>
		</div>
	</Container>
</Section>

<!-- ========================================================= -->
<!-- PRICING -->
<!-- ========================================================= -->

<Section tone="canvas" padding="none" class="pb-20 sm:pb-28">
	<Container size="xl">
		<div class="grid items-stretch gap-5 lg:grid-cols-3">
			{#each tiers as tier, i (tier.name)}
				<div
					class={[
						'relative flex flex-col rounded-3xl border bg-white p-6 shadow-sm transition-all duration-200 sm:p-7 dark:bg-slate-900',
						tier.featured
							? 'border-brand-300 shadow-lg shadow-brand-500/10 ring-2 ring-brand-500/20 dark:border-brand-700 dark:bg-slate-900'
							: 'border-slate-200 hover:border-slate-300 hover:shadow-md dark:border-slate-800 dark:hover:border-slate-700'
					].join(' ')}
				>
					<!-- Featured badge -->
					{#if tier.featured}
						<div class="absolute -top-3 left-1/2 -translate-x-1/2">
							<Badge tone="accent" size="sm">Most popular</Badge>
						</div>
					{/if}

					<!-- Tier header -->
					<div>
						<div class="flex items-start justify-between gap-4">
							<div>
								<p class="text-xs font-bold tracking-wider text-brand-600 uppercase dark:text-brand-400">
									{String(i + 1).padStart(2, '0')}
								</p>

								<h2 class="mt-2 text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
									{tier.name}
								</h2>
							</div>

							<div
								class={[
									'flex size-10 items-center justify-center rounded-xl',
									tier.featured
										? 'bg-brand-50 text-brand-600 dark:bg-brand-950/50 dark:text-brand-400'
										: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
								].join(' ')}
							>
								<Icon
									name={tier.name === 'Solo'
										? 'user'
										: tier.name === 'Studio'
											? 'users'
											: 'building'}
									class="size-5"
								/>
							</div>
						</div>

						<p class="mt-2 text-sm text-slate-500 dark:text-slate-400">
							{tier.label}
						</p>
					</div>

					<!-- Price -->
					<div class="mt-7 border-y border-slate-100 py-6 dark:border-slate-800">
						<div class="flex items-end gap-1">
							<span
								class="text-4xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100"
							>
								{tier.priceMonthly}
							</span>

							<span class="mb-1.5 text-sm font-medium text-slate-500 dark:text-slate-400">
								SAR / month
							</span>
						</div>

						<p class="mt-2 text-xs text-slate-500 dark:text-slate-400">
							{tier.description}
						</p>
					</div>

					<!-- Features -->
					<div class="flex-1">
						<p class="mt-6 text-[10px] font-bold tracking-[0.16em] text-slate-400 uppercase">
							Includes
						</p>

						<ul class="mt-4 space-y-3">
							{#each tier.features as feature (feature)}
								<li class="flex items-start gap-3">
									<span
										class="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-600 dark:bg-brand-950/50 dark:text-brand-400"
									>
										<Icon name="check" class="size-3" />
									</span>

									<span class="text-sm text-slate-700 dark:text-slate-300">
										{feature}
									</span>
								</li>
							{/each}
						</ul>
					</div>

					<!-- CTA -->
					<div class="mt-8">
						<Button
							size="lg"
							variant={tier.featured ? 'primary' : 'outline'}
							href={resolve('/register')}
							class="w-full"
						>
							Start with {tier.name}
						</Button>
					</div>
				</div>
			{/each}
		</div>

		<!-- Pricing note -->
		<div
			class="mx-auto mt-8 flex max-w-3xl items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900/60"
		>
			<Icon name="info" class="mt-0.5 size-4 shrink-0 text-slate-400" />

			<p class="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
				These are illustrative marketing prices. Subscription and billing data is
				managed separately inside the authenticated product and may change before launch.
			</p>
		</div>
	</Container>
</Section>

<!-- ========================================================= -->
<!-- WHAT'S INCLUDED -->
<!-- ========================================================= -->

<Section
	tone="sunken"
	class="border-y border-slate-200 py-16 sm:py-24 dark:border-slate-800"
>
	<Container size="xl">
		<SectionHeading
			align="center"
			eyebrow="Every plan"
			title="The NOVA foundation stays the same"
			subtitle="Your plan determines scale and access — not whether you get the core operating system."
		/>

		<div class="mx-auto mt-12 grid max-w-5xl gap-4 sm:grid-cols-2 lg:grid-cols-4">
			{#each [
				{
					icon: 'calendar',
					title: 'Bookings',
					body: 'Appointments and real-time availability.'
				},
				{
					icon: 'users',
					title: 'Queue',
					body: 'Walk-ins and appointments in one line.'
				},
				{
					icon: 'chat-bubble',
					title: 'WhatsApp',
					body: 'Confirmations and reminders built in.'
				},
				{
					icon: 'credit-card',
					title: 'Payments',
					body: 'Deposits through your payment provider.'
				}
			] as item (item.title)}
				<div
					class="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
				>
					<div
						class="flex size-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-950/50 dark:text-brand-400"
					>
						<Icon name={item.icon} class="size-5" />
					</div>

					<h3 class="mt-4 text-sm font-bold text-slate-900 dark:text-slate-100">
						{item.title}
					</h3>

					<p class="mt-1.5 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
						{item.body}
					</p>
				</div>
			{/each}
		</div>
	</Container>
</Section>

<!-- ========================================================= -->
<!-- FAQ -->
<!-- ========================================================= -->

<Section tone="canvas" class="py-16 sm:py-24">
	<Container size="md">
		<SectionHeading
			align="center"
			eyebrow="Questions"
			title="Pricing, without the fine print."
			subtitle="A few answers before you get started."
		/>

		<div class="mt-10 space-y-3">
			{#each faqs as item, i (item.q)}
				<details
					class="group overflow-hidden rounded-2xl border border-slate-200 bg-white transition-shadow open:shadow-sm dark:border-slate-800 dark:bg-slate-900"
				>
					<summary
						class="flex cursor-pointer list-none items-center justify-between gap-5 px-5 py-5 text-sm font-semibold text-slate-900 marker:content-none dark:text-slate-100"
					>
						<span>{item.q}</span>

						<span
							class="flex size-7 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500 transition-transform duration-200 group-open:rotate-45 dark:bg-slate-800 dark:text-slate-400"
						>
							<Icon name="plus" class="size-4" />
						</span>
					</summary>

					<div class="border-t border-slate-100 px-5 pb-5 pt-4 dark:border-slate-800">
						<p class="text-sm leading-relaxed text-slate-600 dark:text-slate-400">
							{item.a}
						</p>
					</div>
				</details>
			{/each}
		</div>
	</Container>
</Section>

<!-- ========================================================= -->
<!-- CTA -->
<!-- ========================================================= -->

<Section tone="dark" class="py-16 sm:py-24">
	<Container size="md" class="text-center">
		<div
			class="mx-auto flex size-12 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.06]"
		>
			<Icon name="sparkles" class="size-5 text-brand-400" />
		</div>

		<h2 class="mt-6 text-display-lg font-bold tracking-tight text-white">
			Ready to run your business on NOVA?
		</h2>

		<p class="mt-4 text-body-lg text-white/70">
			Start with the plan that fits today. Move up when your business grows.
		</p>

		<div class="mt-8 flex flex-wrap justify-center gap-3">
			<Button size="lg" variant="inverse" href={resolve('/register')}>
				Start 14-day free trial
			</Button>

			<Button size="lg" variant="outline-inverse" href={resolve('/features')}>
				Explore features
			</Button>
		</div>
	</Container>
</Section>
