<script>
	/**
	 * @type {{
	 *   title: string,
	 *   subtitle?: string|null,
	 *   actions?: import('svelte').Snippet
	 * }}
	 */
	let { title, subtitle = null, actions } = $props();
</script>

<div class="flex flex-wrap items-start justify-between gap-4 pb-6">
	<div>
		<h1 class="text-xl font-semibold text-slate-900 dark:text-slate-100">{title}</h1>
		{#if subtitle}
			<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>
		{/if}
	</div>
	{#if actions}
		<div class="flex items-center gap-2">{@render actions()}</div>
	{/if}
</div>
