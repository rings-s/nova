<script>
	import { resolve } from '$app/paths';
	import Button from '$lib/components/ui/Button.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import Section from '$lib/components/marketing/Section.svelte';
	import SectionHeading from '$lib/components/marketing/SectionHeading.svelte';
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';

	/** @type {{ icon: import('$lib/components/ui/Icon.svelte').IconName, title: string, body: string }[]} */
	const principles = [
		{
			icon: 'globe',
			title: 'Arabic-first, not translated after',
			body: 'Every business, service and provider name is stored in Arabic and English from the first record — the data model requires both, not just the interface.'
		},
		{
			icon: 'chat-bubble',
			title: 'WhatsApp is the channel, not an add-on',
			body: 'Confirmations, reminders and receipts go where a customer already is, built directly into the booking flow rather than bolted on as a notification plugin.'
		},
		{
			icon: 'calendar',
			title: 'SAR and Riyadh time, by default',
			body: 'Pricing, schedules and payouts default to the GCC. Nothing here started as a template built for somewhere else and adapted.'
		}
	];
</script>

<svelte:head><title>About — NOVA</title></svelte:head>

<Section tone="canvas">
	<GradientBlob variant="corner" />
	<Container size="md">
		<SectionHeading
			align="center"
			eyebrow="About"
			title="Built for salons and spas across the GCC"
			subtitle="Booking, walk-ins, WhatsApp and payments are usually four separate tools stitched together by hand. NOVA exists to make that one platform, built around how a salon actually runs its day."
		/>
	</Container>
</Section>

<Section tone="sunken">
	<Container size="lg">
		<SectionHeading align="center" title="How we think about it" />
		<div class="mt-12 grid gap-8 sm:grid-cols-3">
			{#each principles as item (item.title)}
				<div class="text-center">
					<div
						class="mx-auto inline-flex size-12 items-center justify-center rounded-full bg-white text-brand-600 shadow-sm dark:bg-slate-900 dark:text-brand-400"
					>
						<Icon name={item.icon} class="size-6" />
					</div>
					<h3 class="mt-4 font-semibold text-slate-900 dark:text-slate-100">{item.title}</h3>
					<p class="mt-2 text-sm text-slate-500 dark:text-slate-400">{item.body}</p>
				</div>
			{/each}
		</div>
	</Container>
</Section>

<Section tone="dark">
	<Container size="md" class="text-center">
		<h2 class="text-display-lg font-semibold tracking-tight">Bring your salon onto NOVA</h2>
		<p class="mt-4 text-body-lg text-white/80">Set up your storefront in minutes.</p>
		<div class="mt-8 flex flex-wrap justify-center gap-3">
			<Button size="lg" variant="inverse" href={resolve('/register')}>Get started</Button>
			<Button size="lg" variant="outline-inverse" href={resolve('/discover')}>Find a salon</Button>
		</div>
	</Container>
</Section>
