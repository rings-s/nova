<script>
	/**
	 * @type {{ name: string, src?: string|null, size?: 'sm'|'md'|'lg' }}
	 */
	let { name, src = null, size = 'md' } = $props();

	const sizeClasses = { sm: 'size-8 text-xs', md: 'size-10 text-sm', lg: 'size-14 text-lg' };

	// A stable hue per name, so the same person keeps the same color everywhere.
	const hues = [
		'bg-brand-100 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300',
		'bg-plum-100 text-plum-700 dark:bg-plum-500/15 dark:text-plum-300',
		'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300',
		'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
		'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300'
	];
	let hue = $derived.by(() => {
		let hash = 0;
		for (const ch of name) hash = (Math.imul(hash, 31) + ch.charCodeAt(0)) | 0;
		return hues[Math.abs(hash) % hues.length];
	});

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
	<img
		{src}
		alt={name}
		class={`rounded-full object-cover ring-2 ring-surface ${sizeClasses[size]}`}
	/>
{:else}
	<div
		class={`flex shrink-0 items-center justify-center rounded-full font-semibold ring-2 ring-surface ${hue} ${sizeClasses[size]}`}
		title={name}
	>
		{initials}
	</div>
{/if}
