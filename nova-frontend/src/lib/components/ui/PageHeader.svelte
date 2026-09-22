<script>
	/**
	 * The top of every dashboard and account page: optional eyebrow (the
	 * section the page belongs to), the page title, one line of context, and
	 * the page's primary actions aligned to the title's baseline.
	 *
	 * @type {{
	 *   title: string,
	 *   subtitle?: string|null,
	 *   eyebrow?: string|null,
	 *   actions?: import('svelte').Snippet
	 * }}
	 */
	let { title, subtitle = null, eyebrow = null, actions } = $props();
</script>

<header class="flex flex-wrap items-end justify-between gap-x-6 gap-y-4 pb-6 sm:pb-8">
	<div class="min-w-0">
		{#if eyebrow}
			<p class="mb-1.5 text-xs font-semibold tracking-wider text-accent uppercase">{eyebrow}</p>
		{/if}
		<h1 class="text-2xl font-semibold tracking-tight text-fg sm:text-[1.75rem] sm:leading-9">
			{title}
		</h1>
		{#if subtitle}
			<p class="mt-1.5 max-w-2xl text-sm text-fg-muted sm:text-[15px]">{subtitle}</p>
		{/if}
	</div>
	{#if actions}
		<div class="flex flex-wrap items-center gap-2">{@render actions()}</div>
	{/if}
</header>
