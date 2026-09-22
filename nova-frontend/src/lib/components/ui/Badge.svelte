<script>
	/**
	 * Status and metadata pill. `dot` prefixes a colored status dot — use it
	 * for live state (confirmed, in service), leave it off for plain labels.
	 *
	 * @type {{
	 *   tone?: 'neutral'|'success'|'warning'|'error'|'info'|'accent',
	 *   size?: 'sm'|'md',
	 *   dot?: boolean,
	 *   children?: import('svelte').Snippet,
	 *   class?: string
	 * }}
	 */
	let { tone = 'neutral', size = 'md', dot = false, children, class: className = '' } = $props();

	const toneClasses = {
		neutral: 'bg-surface-muted text-fg-secondary ring-line',
		success:
			'bg-emerald-50 text-emerald-700 ring-emerald-600/15 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-400/20',
		warning:
			'bg-amber-50 text-amber-800 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-400/20',
		error:
			'bg-red-50 text-red-700 ring-red-600/15 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-400/20',
		info: 'bg-sky-50 text-sky-700 ring-sky-600/15 dark:bg-sky-500/10 dark:text-sky-300 dark:ring-sky-400/20',
		accent:
			'bg-brand-50 text-brand-700 ring-brand-600/15 dark:bg-brand-500/10 dark:text-brand-300 dark:ring-brand-400/20'
	};

	const dotClasses = {
		neutral: 'bg-fg-subtle',
		success: 'bg-emerald-500',
		warning: 'bg-amber-500',
		error: 'bg-red-500',
		info: 'bg-sky-500',
		accent: 'bg-brand-500'
	};

	const sizeClasses = { sm: 'h-5 px-2 text-[11px]', md: 'h-6 px-2.5 text-xs' };
</script>

<span
	class={[
		'inline-flex items-center gap-1.5 rounded-full font-medium whitespace-nowrap ring-1 ring-inset',
		toneClasses[tone],
		sizeClasses[size],
		className
	].join(' ')}
>
	{#if dot}<span class={`size-1.5 rounded-full ${dotClasses[tone]}`} aria-hidden="true"></span>{/if}
	{@render children?.()}
</span>
