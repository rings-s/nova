<script>
	import { businessStore } from '$lib/stores/business.svelte.js';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import { resolve } from '$app/paths';

	let businessId = $derived(businessStore.activeBusinessId);

	const sections =
		/** @type {{ title: string, body: string, href: '/app/catalog'|'/app/bookings'|'/app/queue'|'/app/customers'|'/app/analytics'|'/app/billing'|'/app/team' }[]} */ ([
			{
				title: 'Catalog',
				body: 'Manage locations, services and providers.',
				href: '/app/catalog'
			},
			{
				title: 'Bookings',
				body: "Today's day sheet — confirm, check in, and complete visits.",
				href: '/app/bookings'
			},
			{
				title: 'Queue',
				body: 'Manage the live walk-in line.',
				href: '/app/queue'
			},
			{
				title: 'Customers',
				body: 'Search your customer list, and manage consent.',
				href: '/app/customers'
			},
			{
				title: 'Analytics',
				body: 'Charts and breakdowns of how the business is doing.',
				href: '/app/analytics'
			},
			{
				title: 'Billing',
				body: 'Subscription, invoices and payouts.',
				href: '/app/billing'
			},
			{
				title: 'Team',
				body: 'Invite staff and manage roles.',
				href: '/app/team'
			}
		]);
</script>

<svelte:head><title>Dashboard — NOVA</title></svelte:head>

<PageHeader title="Overview" subtitle="Your business at a glance." />

{#if !businessId}
	<Card padding="lg">
		<p class="text-slate-700 dark:text-slate-200">Set up your storefront to get started.</p>
		<Button class="mt-4" href={resolve('/app/catalog')}>Go to Catalog</Button>
	</Card>
{:else}
	<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
		{#each sections as section (section.href)}
			<Card padding="md">
				<h2 class="font-medium text-slate-900 dark:text-slate-100">{section.title}</h2>
				<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">{section.body}</p>
				<Button class="mt-3" size="sm" variant="outline" href={resolve(section.href)}>Open</Button>
			</Card>
		{/each}
	</div>
{/if}
