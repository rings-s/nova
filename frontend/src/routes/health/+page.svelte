<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { api, ApiError } from '$lib/api/client';
	import type { HealthStatus } from '$lib/api/types';
	import { t } from '$lib/i18n';

	let locale = $derived(page.data.locale);
	let state: 'checking' | 'ok' | 'error' = $state('checking');

	onMount(async () => {
		try {
			await api.get<HealthStatus>('/health');
			state = 'ok';
		} catch (error) {
			state = 'error';
			if (error instanceof ApiError) {
				console.error(error.message);
			}
		}
	});
</script>

<svelte:head>
	<title>{t(locale, 'nav.health')}</title>
</svelte:head>

<main>
	<h1>{t(locale, 'nav.health')}</h1>
	<p>{t(locale, `health.${state}`)}</p>
	<a href="/">{t(locale, 'app.title')}</a>
</main>
