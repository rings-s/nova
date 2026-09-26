<script>
	import { t, m } from '$lib/i18n/index.svelte.js';
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
			name: m('Solo'),
			priceMonthly: 149,
			description: m('One location, one provider.'),
			label: m('For independent operators'),
			features: [
				m('Booking & walk-in queue'),
				m('WhatsApp confirmations & reminders'),
				m('Deposits via Moyasar'),
				m('Marketplace listing')
			]
		},
		{
			name: m('Studio'),
			priceMonthly: 349,
			description: m('A small team, multiple providers.'),
			label: m('For growing teams'),
			features: [
				m('Everything in Solo'),
				m('Multiple providers & schedules'),
				m('AI chat assistant for staff'),
				m('Analytics & reporting')
			],
			featured: true
		},
		{
			name: m('Chain'),
			priceMonthly: 799,
			description: m('Multiple locations under one account.'),
			label: m('For multi-location businesses'),
			features: [
				m('Everything in Studio'),
				m('Multiple locations'),
				m('Role-based staff permissions'),
				m('Priority support')
			]
		}
	];

	const faqs = [
		{
			q: m('How does the marketplace commission work?'),
			a: m(
				'A booking that arrives through the NOVA marketplace carries a referral, and a small commission applies to that booking alongside your subscription. Bookings made directly through your own storefront are not affected.'
			)
		},
		{
			q: m('Can I change plans later?'),
			a: m(
				'Yes. Your plan is tied to your business rather than a long-term contract, so you can move up or down as your team and locations change.'
			)
		},
		{
			q: m('Do you take a cut of deposits?'),
			a: m(
				'No. Deposits and payments go through Moyasar under your own account. NOVA does not hold customer funds.'
			)
		},
		{
			q: m('Is there a setup fee?'),
			a: m(
				'No. Creating your storefront, services and providers is self-serve and included with every plan.'
			)
		}
	];

	/** @type {{ icon: import('$lib/components/ui/Icon.svelte').IconName, title: string, body: string }[]} */
	const included = [
		{ icon: 'calendar', title: m('Bookings'), body: m('Appointments and real-time availability.') },
		{ icon: 'users', title: m('Queue'), body: m('Walk-ins and appointments in one line.') },
		{ icon: 'chat-bubble', title: m('WhatsApp'), body: m('Confirmations and reminders built in.') },
		{
			icon: 'credit-card',
			title: m('Payments'),
			body: m('Deposits through your payment provider.')
		}
	];
</script>

<svelte:head>
	<title>{t('Pricing')} — NOVA</title>
	<meta
		name="description"
		content={t(
			"Simple monthly pricing for NOVA's booking, queue, payments and business management platform."
		)}
	/>
</svelte:head>

<!-- ========================================================= -->
<!-- HERO -->
<!-- ========================================================= -->

<Section tone="canvas" padding="tight" class="pt-16 sm:pt-24">
	<GradientBlob variant="hero" />

	<Container size="xl">
		<div class="mx-auto max-w-4xl text-center">
			<p
				class="inline-flex items-center gap-2 rounded-full border border-line bg-surface/80 px-3 py-1 text-xs font-medium text-fg-secondary backdrop-blur"
			>
				<span class="size-1.5 rounded-full bg-brand-500"></span>
				{t('Simple monthly pricing')}
			</p>

			<h1 class="mt-6 text-display-2xl font-semibold tracking-tight text-fg">
				{t('Choose the plan that fits')}
				<span class="text-accent">{t('your business.')}</span>
			</h1>

			<p class="mx-auto mt-6 max-w-2xl text-body-lg text-fg-muted">
				{t(
					'Every plan includes the core NOVA operating system. Start small and expand as your team and locations grow.'
				)}
			</p>

			<div
				class="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-sm font-medium text-fg-muted"
			>
				<span class="flex items-center gap-1.5">
					<Icon name="check" class="size-3.5 text-emerald-500" />
					{t('Billed monthly in SAR')}
				</span>

				<span class="flex items-center gap-1.5">
					<Icon name="check" class="size-3.5 text-emerald-500" />
					{t('No setup fee')}
				</span>

				<span class="flex items-center gap-1.5">
					<Icon name="check" class="size-3.5 text-emerald-500" />
					{t('No long-term contract')}
				</span>
			</div>
		</div>
	</Container>
</Section>

<!-- ========================================================= -->
<!-- PRICING -->
<!-- ========================================================= -->

<Section tone="canvas" padding="none" class="pt-6 pb-20 sm:pb-28">
	<Container size="xl">
		<div class="grid items-stretch gap-5 lg:grid-cols-3">
			{#each tiers as tier, i (tier.name)}
				<div
					class={[
						'relative flex flex-col rounded-panel border bg-surface p-6 transition-[border-color,box-shadow] duration-base ease-out-premium sm:p-8',
						tier.featured
							? 'border-brand-300 shadow-raised ring-4 ring-brand-500/10 dark:border-brand-500/40'
							: 'border-line shadow-card hover:border-line-strong hover:shadow-raised'
					].join(' ')}
				>
					<!-- Featured badge -->
					{#if tier.featured}
						<div class="absolute -top-3 left-1/2 -translate-x-1/2">
							<Badge tone="accent" size="sm">{t('Most popular')}</Badge>
						</div>
					{/if}

					<!-- Tier header -->
					<div>
						<div class="flex items-start justify-between gap-4">
							<div>
								<p class="text-xs font-semibold tracking-wider text-accent uppercase">
									{String(i + 1).padStart(2, '0')}
								</p>

								<h2 class="mt-2 text-2xl font-semibold tracking-tight text-fg">
									{t(tier.name)}
								</h2>
							</div>

							<div
								class={[
									'flex size-10 items-center justify-center rounded-control',
									tier.featured ? 'bg-accent-soft text-accent' : 'bg-surface-muted text-fg-muted'
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

						<p class="mt-2 text-sm text-fg-muted">
							{t(tier.label)}
						</p>
					</div>

					<!-- Price -->
					<div class="mt-7 border-y border-line-subtle py-6">
						<div class="flex items-end gap-1">
							<span class="text-4xl font-semibold tracking-tight text-fg tabular-nums">
								{tier.priceMonthly}
							</span>

							<span class="mb-1.5 text-sm font-medium text-fg-muted">{t('SAR / month')}</span>
						</div>

						<p class="mt-2 text-xs text-fg-muted">
							{t(tier.description)}
						</p>
					</div>

					<!-- Features -->
					<div class="flex-1">
						<p class="mt-6 text-xs font-semibold tracking-wider text-fg-subtle uppercase">
							{t('Includes')}
						</p>

						<ul class="mt-4 space-y-3">
							{#each tier.features as feature (feature)}
								<li class="flex items-start gap-3">
									<span
										class="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent"
									>
										<Icon name="check" class="size-3" />
									</span>

									<span class="text-sm text-fg-secondary">
										{t(feature)}
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
							href={`${resolve('/register')}?as=business`}
							class="w-full"
						>
							{t('Start with {plan}', { plan: t(tier.name) })}
						</Button>
					</div>
				</div>
			{/each}
		</div>

		<!-- Pricing note -->
		<div
			class="mx-auto mt-8 flex max-w-3xl items-start gap-3 rounded-card border border-line bg-surface-sunken p-4"
		>
			<Icon name="info" class="mt-0.5 size-4 text-fg-subtle" />

			<p class="text-xs leading-relaxed text-fg-muted">
				{t(
					'These are illustrative marketing prices. Subscription and billing data is managed separately inside the authenticated product and may change before launch.'
				)}
			</p>
		</div>
	</Container>
</Section>

<!-- ========================================================= -->
<!-- WHAT'S INCLUDED -->
<!-- ========================================================= -->

<Section tone="sunken" class="border-y border-line">
	<Container size="xl">
		<SectionHeading
			align="center"
			eyebrow={t('Every plan')}
			title={t('The NOVA foundation stays the same')}
			subtitle={t(
				'Your plan determines scale and access — not whether you get the core operating system.'
			)}
		/>

		<div class="mx-auto mt-12 grid max-w-5xl gap-4 sm:grid-cols-2 lg:grid-cols-4">
			{#each included as item (item.title)}
				<div class="rounded-card border border-line bg-surface p-5 shadow-card">
					<div
						class="flex size-10 items-center justify-center rounded-control bg-accent-soft text-accent"
					>
						<Icon name={item.icon} class="size-5" />
					</div>

					<h3 class="mt-4 text-sm font-semibold text-fg">
						{t(item.title)}
					</h3>

					<p class="mt-1.5 text-sm leading-relaxed text-fg-muted">
						{t(item.body)}
					</p>
				</div>
			{/each}
		</div>
	</Container>
</Section>

<!-- ========================================================= -->
<!-- FAQ -->
<!-- ========================================================= -->

<Section tone="canvas">
	<Container size="md">
		<SectionHeading
			align="center"
			eyebrow={t('Questions')}
			title={t('Pricing, without the fine print.')}
			subtitle={t('A few answers before you get started.')}
		/>

		<div class="mt-10 space-y-3">
			{#each faqs as item (item.q)}
				<details
					class="group overflow-hidden rounded-card border border-line bg-surface shadow-card transition-shadow open:shadow-raised"
				>
					<summary
						class="flex cursor-pointer list-none items-center justify-between gap-5 rounded-card px-5 py-4 text-[15px] font-semibold text-fg focus-ring marker:content-none [&::-webkit-details-marker]:hidden"
					>
						<span>{t(item.q)}</span>

						<span
							class="flex size-7 shrink-0 items-center justify-center rounded-control bg-surface-muted text-fg-muted transition-transform duration-200 group-open:rotate-45"
						>
							<Icon name="plus" class="size-4" />
						</span>
					</summary>

					<div class="border-t border-line-subtle px-5 pt-4 pb-5">
						<p class="text-sm leading-relaxed text-fg-muted">
							{t(item.a)}
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

<Section
	tone="dark"
	padding="tight"
	class="mx-4 my-16 rounded-panel sm:mx-6 lg:mx-auto lg:max-w-7xl"
>
	<GradientBlob variant="corner" />
	<Container size="md" class="relative py-8 text-center sm:py-12">
		<h2 class="text-display-lg font-semibold tracking-tight text-white">
			{t('Ready to run your business on NOVA?')}
		</h2>

		<p class="mt-4 text-body-lg text-white/80">
			{t('Start with the plan that fits today. Move up when your business grows.')}
		</p>

		<div class="mt-8 flex flex-wrap justify-center gap-3">
			<Button size="lg" variant="inverse" href={`${resolve('/register')}?as=business`}>
				{t('Start 14-day free trial')}
			</Button>

			<Button size="lg" variant="outline-inverse" href={resolve('/features')}>
				{t('Explore features')}
			</Button>
		</div>
	</Container>
</Section>
