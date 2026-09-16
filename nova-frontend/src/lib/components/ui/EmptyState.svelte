<script>
	/**
	 * @type {{
	 *   title: string,
	 *   description?: string|null,
	 *   action?: import('svelte').Snippet,
	 *   icon?: import('svelte').Snippet
	 * }}
	 */
	let { title, description = null, action, icon } = $props();
</script>

<div
	class="flex flex-col items-center gap-3 rounded-xl border border-dashed border-slate-300 px-6 py-12 text-center dark:border-slate-700"
>
	{#if icon}
		<div class="text-slate-400 dark:text-slate-500">{@render icon()}</div>
	{/if}
	<div>
		<p class="font-medium text-slate-900 dark:text-slate-100">{title}</p>
		{#if description}
			<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">{description}</p>
		{/if}
	</div>
	{#if action}
		<div class="mt-1">{@render action()}</div>
	{/if}
</div>
