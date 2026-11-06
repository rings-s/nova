<script>
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import { page } from '$app/state';
	import { isPublicChromeRoute } from '$lib/utils/routeChrome.js';
	import SiteHeader from '$lib/components/layout/SiteHeader.svelte';
	import Footer from '$lib/components/layout/Footer.svelte';
	import ToastContainer from '$lib/components/ui/ToastContainer.svelte';
	import { i18n } from '$lib/i18n/index.svelte.js';
	import { onMount, untrack } from 'svelte';
	import { pwaInfo } from 'virtual:pwa-info';
	import { pwaAssetsHead } from 'virtual:pwa-assets/head';
	import { registerSW } from 'virtual:pwa-register';

	let { children, data } = $props();

	// The language the server rendered in. Set once, before anything renders;
	// after that only the language switch (`setLocale`) changes it.
	untrack(() => (i18n.locale = data.locale));

	let showFooter = $derived(isPublicChromeRoute(page.url.pathname));
	// The dashboard is its own shell with its own <main>; wrapping it in this
	// one would nest two main landmarks and put its sidebar inside "main".
	let isDashboard = $derived(page.url.pathname.startsWith('/app'));

	// The tab keeps the brand SVG favicon; from the generated set (see
	// pwa-assets.config.js) only the home-screen icons go in the head.
	const appIcons = pwaAssetsHead.links.filter((link) => link.rel !== 'icon');

	// `pwaInfo` is undefined when the PWA plugin is disabled.
	onMount(() => {
		if (pwaInfo) registerSW({ immediate: true });
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	{#if pwaInfo}
		<link rel="manifest" href={pwaInfo.webManifest.href} />
	{/if}
	{#if pwaAssetsHead.themeColor}
		<meta name="theme-color" content={pwaAssetsHead.themeColor.content} />
	{/if}
	{#each appIcons as link (link.href)}
		<link {...link} />
	{/each}
</svelte:head>

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
