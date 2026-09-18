<script>
	import { themeStore } from '$lib/stores/theme.svelte.js';
	import Icon from './Icon.svelte';

	/** @type {{ class?: string }} */
	let { class: className = '' } = $props();
</script>

<button
	type="button"
	onclick={() => themeStore.toggle()}
	class={[
		'inline-flex size-9 items-center justify-center rounded-lg text-slate-600 transition-colors hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800',
		className
	].join(' ')}
	aria-label={themeStore.isDark ? 'Switch to light mode' : 'Switch to dark mode'}
	title={themeStore.isDark ? 'Switch to light mode' : 'Switch to dark mode'}
>
	<Icon name={themeStore.isDark ? 'sun' : 'moon'} class="size-5" />
</button>
