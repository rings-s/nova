<script>
	import { t } from '$lib/i18n/index.svelte.js';
	import { onMount } from 'svelte';
	import { themeStore } from '$lib/stores/theme.svelte.js';
	import Icon from './Icon.svelte';
	import { iconButton } from './styles.js';

	/** @type {{ class?: string }} */
	let { class: className = '' } = $props();

	// The theme lives in this browser's storage, so the server cannot know it.
	// Both icons are rendered, and the `.dark` class on <html> picks one, so the
	// server's HTML and the browser's match (`hydration_html_changed` otherwise,
	// and the wrong icon until the first click). The label names the mode only
	// once this runs in the browser, for the same reason.
	let mounted = $state(false);
	onMount(() => (mounted = true));

	let label = $derived(
		!mounted
			? t('Switch theme')
			: themeStore.isDark
				? t('Switch to light mode')
				: t('Switch to dark mode')
	);
</script>

<button
	type="button"
	onclick={() => themeStore.toggle()}
	class={[`${iconButton} size-9`, className].join(' ')}
	aria-label={label}
	title={label}
>
	<Icon name="moon" class="size-5 dark:hidden" />
	<Icon name="sun" class="hidden size-5 dark:block" />
</button>
