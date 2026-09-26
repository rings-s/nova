<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/** @type {{ size?: 'sm'|'md'|'lg', label?: string|null, class?: string }} */
	let { size = 'md', label = null, class: className = '' } = $props();

	const sizeClasses = { sm: 'size-4', md: 'size-6', lg: 'size-9' };
</script>

<svg
	class={`animate-spin text-accent ${sizeClasses[size]} ${className}`}
	viewBox="0 0 24 24"
	fill="none"
	role="status"
	aria-label={label ?? t('Loading')}
>
	<circle class="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" />
	<path
		d="M22 12a10 10 0 0 0-10-10"
		stroke="currentColor"
		stroke-width="3"
		stroke-linecap="round"
	/>
</svg>
