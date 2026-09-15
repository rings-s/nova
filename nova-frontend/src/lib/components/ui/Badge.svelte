<script>
	/**
	 * @type {{
	 *   tone?: 'neutral'|'success'|'warning'|'error'|'info'|'accent',
	 *   size?: 'sm'|'md',
	 *   children?: import('svelte').Snippet
	 * }}
	 */
	let { tone = 'neutral', size = 'md', children } = $props();

	const toneClasses = {
		neutral: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
		success: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
		warning: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
		error: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
		info: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300',
		accent: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
	};

	const sizeClasses = { sm: 'px-2 py-0.5 text-xs', md: 'px-2.5 py-1 text-xs' };
</script>

<span
	class={[
		'inline-flex items-center gap-1 rounded-full font-medium whitespace-nowrap',
		toneClasses[tone],
		sizeClasses[size]
	].join(' ')}
>
	{@render children?.()}
</span>
