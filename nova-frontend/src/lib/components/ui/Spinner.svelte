<script>
	/** @type {{ size?: 'sm'|'md'|'lg', label?: string }} */
	let { size = 'md', label = 'Loading' } = $props();

	const sizeClasses = { sm: 'size-4', md: 'size-6', lg: 'size-10' };
</script>

<svg
	class={`animate-spin text-rose-600 ${sizeClasses[size]}`}
	viewBox="0 0 24 24"
	fill="none"
	role="status"
	aria-label={label}
>
	<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
	<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
</svg>
