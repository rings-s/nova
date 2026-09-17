<script>
	/**
	 * @type {{
	 *   size?: 'md'|'lg'|'xl',
	 *   class?: string,
	 *   children?: import('svelte').Snippet
	 * }}
	 */
	let { size = 'lg', class: className = '', children } = $props();

	const sizeClasses = { md: 'max-w-3xl', lg: 'max-w-6xl', xl: 'max-w-7xl' };
</script>

<div class={['mx-auto w-full px-4 sm:px-6 lg:px-8', sizeClasses[size], className].join(' ')}>
	{@render children?.()}
</div>
