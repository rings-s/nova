<script>
	import { t, m } from '$lib/i18n/index.svelte.js';
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
			label: m('Smart scheduling'),
			title: m('Appointments that never collide.'),
			body: m(
				'NOVA calculates availability across providers, services and branches in real time. A slot is temporarily reserved the moment checkout begins, preventing double bookings before they happen.'
			),
			points: [
				m('Per-provider schedules and skills'),
				m('Real-time availability calculation'),
				m('Temporary checkout holds')
			]
		},
		{
			number: '02',
			icon: 'users',
			label: m('Queue management'),
			title: m('Turn waiting into a system.'),
			body: m(
				'Appointments and walk-ins operate from the same operational layer. Your front desk sees exactly who is next, who is waiting and what needs attention.'
			),
			points: [
				m('Unified booking and walk-in queue'),
				m('Live customer position'),
				m('One-click call-next workflow')
			]
		},
		{
			number: '03',
			icon: 'chat-bubble',
			label: m('Customer communication'),
			title: m('Meet customers where they already are.'),
			body: m(
				'Keep customers informed through WhatsApp without forcing them into another application. Confirmations, reminders and receipts become part of the booking experience.'
			),
			points: [
				m('Automatic confirmations'),
				m('Appointment reminders'),
				m('Receipts and booking updates')
			]
		},
		{
			number: '04',
			icon: 'credit-card',
			label: m('Payments'),
			title: m('Protect every appointment.'),
			body: m(
				'Require a configurable deposit before confirming a booking. Payments are securely processed through Moyasar while NOVA keeps your booking state synchronized.'
			),
			points: [
				m('Configurable deposit percentage'),
				m('Moyasar payment processing'),
				m('Clear payment state per booking')
			]
		},
		{
			number: '05',
			icon: 'globe',
			label: m('Discovery'),
			title: m('Give your business another front door.'),
			body: m(
				'Businesses can opt into the NOVA marketplace and become discoverable by customers searching for services, locations and availability.'
			),
			points: [
				m('Search by city and service'),
				m('Public business storefront'),
				m('Booking referral tracking')
			]
		},
		{
			number: '06',
			icon: 'sparkles',
			label: m('Intelligence'),
			title: m('Ask your business anything.'),
			body: m(
				'The NOVA assistant lets staff interact with operational data using natural language. Responses are grounded in real tool results instead of invented numbers.'
			),
			points: [
				m('Grounded in your business data'),
				m('Role-based access'),
				m('Actions require staff confirmation')
			]
		},
		{
			number: '07',
			icon: 'shield-check',
			label: m('Local by design'),
			title: m('Built for Arabic and English from day one.'),
			body: m(
				'Every important business record can carry Arabic and English values from its first creation. NOVA is designed around the operational reality of businesses in the region.'
			),
			points: [
				m('Arabic and English records'),
				m('RTL and LTR ready'),
				m('Designed for regional businesses')
			]
		}
	];

	/** @type {{ n: number, label: string, s: string, t: 'accent'|'info'|'neutral' }[]} */
	const queueSample = [
		{ n: 1, label: m('Noura A.'), s: m('In service'), t: 'accent' },
		{ n: 2, label: m('Sara M.'), s: m('Called'), t: 'info' },
		{ n: 3, label: m('Reem K.'), s: m('Waiting'), t: 'neutral' },
		{ n: 4, label: m('Huda S.'), s: m('Waiting'), t: 'neutral' }
	];
</script>

<svelte:head>
	<title>{t('Features')} — NOVA</title>
	<meta
		name="description"
		content={t('Booking, queues, payments, messaging and business intelligence in one platform.')}
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
			{t('The NOVA platform')}
		</p>
		<h1 class="mx-auto mt-6 max-w-4xl text-display-2xl font-semibold tracking-tight text-fg">
			{t('One operating system for')}
			<span
				class="text-transparent"
				style="background-image: var(--gradient-hero); -webkit-background-clip: text; background-clip: text;"
				>{t('your front desk.')}</span
			>
		</h1>
		<p class="mx-auto mt-6 max-w-2xl text-body-lg text-fg-muted">
			{t(
				'Bookings, queues, customer messages, payments and insight — designed to work together instead of becoming another collection of disconnected tools.'
			)}
		</p>
		<div class="mt-9 flex flex-wrap justify-center gap-3">
			<Button size="lg" href={`${resolve('/register')}?as=business`}>{t('Start free trial')}</Button
			>
			<Button size="lg" variant="outline" href={resolve('/pricing')}>
				{t('See pricing')}
				<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
			</Button>
		</div>

		<!-- Section index -->
		<nav
			class="mx-auto mt-14 flex max-w-4xl flex-wrap justify-center gap-2"
			aria-label={t('Features')}
		>
			{#each sections as section (section.number)}
				<a
					href={`#feature-${section.number}`}
					class="inline-flex h-8 items-center gap-2 rounded-full border border-line bg-surface px-3.5 text-xs font-medium text-fg-secondary focus-ring transition-colors hover:border-line-strong hover:text-fg"
				>
					<Icon name={section.icon} class="size-3.5 text-accent" />
					{t(section.label)}
				</a>
			{/each}
		</nav>
	</Container>
</section>

<!-- One illustration per feature, built from the app's own components. -->
{#snippet visual(/** @type {string} */ number)}
	{#if number === '01'}
		<div class="space-y-3">
			<p class="text-xs font-semibold tracking-wider text-fg-subtle uppercase">
				{t('Tuesday · Morning')}
			</p>
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
				{t('10:00 held for you · 9:42 left')}
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
					<span class="flex-1 text-sm font-medium text-fg">{t(row.label)}</span>
					<Badge tone={row.t} size="sm" dot>{t(row.s)}</Badge>
				</li>
			{/each}
		</ul>
	{:else if number === '03'}
		<div class="mx-auto max-w-xs space-y-2">
			<div
				class="rounded-card rounded-ss-sm bg-emerald-600 px-4 py-3 text-sm text-white shadow-card"
			>
				<p class="font-semibold">{t('Lumière Spa')}</p>
				<p class="mt-1 text-white/90">
					{t('Your facial is confirmed for Tue 10:00 at Olaya branch. Reply 1 to reschedule.')}
				</p>
				<p class="mt-1 text-end text-[10px] text-white/70">09:41 ✓✓</p>
			</div>
			<div
				class="ms-auto w-fit rounded-card rounded-se-sm bg-surface px-4 py-2 text-sm text-fg shadow-card"
			>
				{t('Thank you!')}
			</div>
		</div>
	{:else if number === '04'}
		<div class="mx-auto max-w-xs rounded-card border border-line bg-surface p-4 shadow-card">
			<div class="flex justify-between text-sm">
				<span class="text-fg-muted">{t('Signature facial')}</span><span
					class="font-medium text-fg tabular-nums">{t('SAR {amount}', { amount: 350 })}</span
				>
			</div>
			<div class="mt-2 flex justify-between text-sm">
				<span class="text-fg-muted">{t('Deposit ({percent}%)', { percent: 30 })}</span><span
					class="font-semibold text-fg tabular-nums">{t('SAR {amount}', { amount: 105 })}</span
				>
			</div>
			<div
				class="mt-4 flex h-10 items-center justify-center rounded-control bg-slate-900 text-sm font-medium text-white dark:bg-white dark:text-slate-900"
			>
				{t('Pay with Apple Pay')}
			</div>
			<p class="mt-2 text-center text-[11px] text-fg-muted">
				{t('Mada · Visa · Mastercard via Moyasar')}
			</p>
		</div>
	{:else if number === '05'}
		<div class="space-y-2">
			<div
				class="flex h-10 items-center gap-2 rounded-control border border-line-strong bg-surface px-3 text-sm text-fg-subtle"
			>
				<Icon name="search" class="size-4" />
				{t('Hammam in Riyadh')}
			</div>
			{#each [[t('Lumière Spa'), t( 'Olaya · {km} km', { km: 1.2 } ), t( 'SAR {amount}', { amount: 180 } )], [t('Rose Hammam'), t( 'Al Malqa · {km} km', { km: 3.4 } ), t( 'SAR {amount}', { amount: 220 } )]] as row (row[0])}
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
				{t('How did Olaya do last week?')}
			</div>
			<div
				class="w-fit max-w-[90%] rounded-card rounded-ss-sm border border-line bg-surface px-4 py-3 text-sm text-fg shadow-card"
			>
				{t('Revenue was {amount}, up 12%. Tuesday mornings were 86% booked.', {
					amount: t('SAR {amount}', { amount: '18,420' })
				})}
				<p class="mt-2 inline-flex items-center gap-1 text-[11px] text-fg-muted">
					<Icon name="chart-bar" class="size-3" />
					{t('From the revenue report')}
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
						<span class="text-fg-muted">{t(section.label)}</span>
					</p>
					<h2 class="mt-5 max-w-xl text-display-lg font-semibold tracking-tight text-fg">
						{t(section.title)}
					</h2>
					<p class="mt-5 max-w-xl text-body-lg text-fg-muted">{t(section.body)}</p>
					<ul class="mt-8 space-y-3">
						{#each section.points as point (point)}
							<li class="flex items-center gap-3 text-sm font-medium text-fg-secondary">
								<span
									class="flex size-6 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent"
								>
									<Icon name="check" class="size-3.5" />
								</span>
								{t(point)}
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
								<span class="text-sm font-semibold text-fg">{t(section.label)}</span>
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
			{t('Your next customer is already looking.')}
		</h2>
		<p class="mx-auto mt-4 max-w-xl text-body-lg text-white/80">
			{t('Give them a faster way to discover your business, book a service and stay connected.')}
		</p>
		<div class="mt-8 flex justify-center">
			<Button size="lg" variant="inverse" href={`${resolve('/register')}?as=business`}>
				{t('Start with NOVA')}
				<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
			</Button>
		</div>
		<p class="mt-5 text-xs text-white/60">{t('No credit card required · Set up in minutes')}</p>
	</Container>
</Section>
