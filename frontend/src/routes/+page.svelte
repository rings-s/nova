<script lang="ts">
	import { page } from '$app/state';
	import { t } from '$lib/i18n';

	let locale = $derived(page.data.locale);
</script>

<svelte:head>
	<title>{t(locale, 'app.title')}</title>
</svelte:head>

<main>
	<h1>{t(locale, 'app.title')}</h1>
	<p>{t(locale, 'app.tagline')}</p>
	<p>{t(locale, 'app.comingSoon')}</p>

	<nav>
		<a href="/health">{t(locale, 'nav.health')}</a>
		<a href={`?locale=${locale === 'en' ? 'ar' : 'en'}`}>
			{t(locale, 'locale.switch')}
		</a>
	</nav>
</main>
