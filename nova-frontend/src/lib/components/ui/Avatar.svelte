<script>
	/**
	 * @type {{ name: string, src?: string|null, size?: 'sm'|'md'|'lg' }}
	 */
	let { name, src = null, size = 'md' } = $props();

	const sizeClasses = { sm: 'size-8 text-xs', md: 'size-10 text-sm', lg: 'size-14 text-lg' };

	let initials = $derived(
		name
			.trim()
			.split(/\s+/)
			.slice(0, 2)
			.map((part) => part[0]?.toUpperCase())
			.join('') || '?'
	);
</script>

{#if src}
	<img {src} alt={name} class={`rounded-full object-cover ${sizeClasses[size]}`} />
{:else}
	<div
		class={`flex items-center justify-center rounded-full bg-brand-100 font-semibold text-brand-700 dark:bg-brand-900/40 dark:text-brand-300 ${sizeClasses[size]}`}
		title={name}
	>
		{initials}
	</div>
{/if}
