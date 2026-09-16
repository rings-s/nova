<script>
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';

	const features = [
		{
			title: 'Book in seconds',
			body: 'Deterministic availability across every branch and provider, with a slot held while checkout completes.'
		},
		{
			title: 'Walk-ins, handled',
			body: 'A QR ticket at the door shares one line with appointments — no separate calendars to reconcile.'
		},
		{
			title: 'WhatsApp, not another app',
			body: 'Confirmations, reminders and receipts land where your customers already are.'
		}
	];
</script>

<svelte:head><title>NOVA — Booking for salons and spas</title></svelte:head>

{#if authStore.isAuthenticated}
	<div class="mx-auto max-w-5xl px-4 py-12 sm:px-6">
		<h1 class="text-2xl font-semibold text-slate-900 dark:text-slate-100">Welcome back</h1>
		{#if authStore.isStaff}
			<p class="mt-2 text-slate-500 dark:text-slate-400">
				Switch businesses from the header, or pick up where you left off.
			</p>
			<Button class="mt-4" href={resolve('/app')}>Go to dashboard</Button>
		{:else}
			<p class="mt-2 text-slate-500 dark:text-slate-400">Your bookings will show up here.</p>
			<div class="mt-4 flex flex-wrap gap-3">
				<Button href={resolve('/bookings')}>My bookings</Button>
				<Button variant="outline" href={resolve('/discover')}>Find a salon</Button>
			</div>
		{/if}
	</div>
{:else}
	<div class="mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-24">
		<div class="max-w-2xl">
			<h1
				class="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl dark:text-slate-100"
			>
				Booking, queues and payments — one platform for your salon.
			</h1>
			<p class="mt-4 text-lg text-slate-500 dark:text-slate-400">
				NOVA brings appointments, walk-ins and WhatsApp messaging together for beauty and wellness
				businesses across the GCC.
			</p>
			<div class="mt-8 flex flex-wrap gap-3">
				<Button size="lg" href={resolve('/register')}>Get started</Button>
				<Button size="lg" variant="outline" href={resolve('/discover')}>Find a salon</Button>
			</div>
		</div>

		<div class="mt-16 grid grid-cols-1 gap-4 sm:grid-cols-3">
			{#each features as feature (feature.title)}
				<Card padding="md">
					<h2 class="font-medium text-slate-900 dark:text-slate-100">{feature.title}</h2>
					<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">{feature.body}</p>
				</Card>
			{/each}
		</div>
	</div>
{/if}
