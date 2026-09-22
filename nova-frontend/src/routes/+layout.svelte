<script>
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import { page } from '$app/state';
	import { isPublicChromeRoute } from '$lib/utils/routeChrome.js';
	import SiteHeader from '$lib/components/layout/SiteHeader.svelte';
	import Footer from '$lib/components/layout/Footer.svelte';
	import ToastContainer from '$lib/components/ui/ToastContainer.svelte';

	let { children } = $props();

	let showFooter = $derived(isPublicChromeRoute(page.url.pathname));
	// The dashboard is its own shell with its own <main>; wrapping it in this
	// one would nest two main landmarks and put its sidebar inside "main".
	let isDashboard = $derived(page.url.pathname.startsWith('/app'));
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<div class={showFooter ? 'flex min-h-dvh flex-col' : 'min-h-dvh'}>
	<SiteHeader />
	{#if isDashboard}
		{@render children()}
	{:else}
		<main class={showFooter ? 'flex-1' : undefined}>
			{@render children()}
		</main>
	{/if}
	{#if showFooter}
		<Footer />
	{/if}
</div>
<ToastContainer />
