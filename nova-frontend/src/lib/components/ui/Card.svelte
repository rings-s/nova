<script>
	/**
	 * @type {{
	 *   padding?: 'none'|'sm'|'md'|'lg',
	 *   header?: import('svelte').Snippet,
	 *   footer?: import('svelte').Snippet,
	 *   children?: import('svelte').Snippet,
	 *   class?: string,
	 *   [key: string]: unknown
	 * }}
	 */
	let { padding = 'md', header, footer, children, class: className = '', ...rest } = $props();

	const paddingClasses = { none: '', sm: 'p-3', md: 'p-5', lg: 'p-7' };
</script>

<div
	class={[
		'rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900',
		className
	].join(' ')}
	{...rest}
>
	{#if header}
		<div class="border-b border-slate-200 px-5 py-3 dark:border-slate-800">
			{@render header()}
		</div>
	{/if}
	<div class={paddingClasses[padding]}>
		{@render children?.()}
	</div>
	{#if footer}
		<div class="border-t border-slate-200 px-5 py-3 dark:border-slate-800">
			{@render footer()}
		</div>
	{/if}
</div>
