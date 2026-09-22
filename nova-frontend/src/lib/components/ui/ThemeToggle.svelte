<script>
	import { themeStore } from '$lib/stores/theme.svelte.js';
	import Icon from './Icon.svelte';
	import { iconButton } from './styles.js';

	/** @type {{ class?: string }} */
	let { class: className = '' } = $props();
</script>

<button
	type="button"
	onclick={() => themeStore.toggle()}
	class={[`${iconButton} size-9`, className].join(' ')}
	aria-label={themeStore.isDark ? 'Switch to light mode' : 'Switch to dark mode'}
	title={themeStore.isDark ? 'Switch to light mode' : 'Switch to dark mode'}
>
	<Icon name={themeStore.isDark ? 'sun' : 'moon'} class="size-5" />
</button>
