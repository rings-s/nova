<script>
	/**
	 * The one surface container. `interactive` adds the hover lift used by
	 * clickable cards (pass `href` to render the whole card as a link).
	 *
	 * @type {{
	 *   padding?: 'none'|'sm'|'md'|'lg',
	 *   interactive?: boolean,
	 *   href?: string|null,
	 *   header?: import('svelte').Snippet,
	 *   footer?: import('svelte').Snippet,
	 *   children?: import('svelte').Snippet,
	 *   class?: string,
	 *   [key: string]: unknown
	 * }}
	 */
	let {
		padding = 'md',
		interactive = false,
		href = null,
		header,
		footer,
		children,
		class: className = '',
		...rest
	} = $props();

	const paddingClasses = { none: '', sm: 'p-4', md: 'p-5', lg: 'p-6 sm:p-7' };

	let classes = $derived(
		[
			'block rounded-card border border-line bg-surface shadow-card',
			interactive || href
				? 'transition-[border-color,box-shadow,transform] duration-base ease-out-premium hover:-translate-y-0.5 hover:border-line-strong hover:shadow-raised focus-ring'
				: '',
			className
		].join(' ')
	);
</script>

{#snippet body()}
	{#if header}
		<div class="border-b border-line px-5 py-4">
			{@render header()}
		</div>
	{/if}
	<div class={paddingClasses[padding]}>
		{@render children?.()}
	</div>
	{#if footer}
		<div class="rounded-b-card border-t border-line bg-surface-sunken px-5 py-3">
			{@render footer()}
		</div>
	{/if}
{/snippet}

{#if href}
	<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- callers pass a resolved path -->
	<a {href} class={classes} {...rest}>{@render body()}</a>
{:else}
	<div class={classes} {...rest}>{@render body()}</div>
{/if}
