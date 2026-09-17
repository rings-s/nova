<script>
	/**
	 * @type {{
	 *   variant?: 'primary'|'secondary'|'outline'|'ghost'|'danger'|'inverse'|'outline-inverse',
	 *   size?: 'sm'|'md'|'lg',
	 *   type?: 'button'|'submit'|'reset',
	 *   href?: string|null,
	 *   disabled?: boolean,
	 *   loading?: boolean,
	 *   fullWidth?: boolean,
	 *   onclick?: (event: MouseEvent) => void,
	 *   children?: import('svelte').Snippet,
	 *   class?: string,
	 *   [key: string]: unknown
	 * }}
	 */
	let {
		variant = 'primary',
		size = 'md',
		type = 'button',
		href = null,
		disabled = false,
		loading = false,
		fullWidth = false,
		onclick,
		children,
		class: className = '',
		...rest
	} = $props();

	const variantClasses = {
		primary: 'bg-brand-600 text-white hover:bg-brand-700 focus-visible:outline-brand-600',
		secondary: 'bg-slate-900 text-white hover:bg-slate-800 focus-visible:outline-slate-900',
		outline:
			'bg-transparent text-slate-900 border border-slate-300 hover:bg-slate-50 focus-visible:outline-slate-400 dark:text-slate-100 dark:border-slate-700 dark:hover:bg-slate-800',
		ghost:
			'bg-transparent text-slate-700 hover:bg-slate-100 focus-visible:outline-slate-400 dark:text-slate-200 dark:hover:bg-slate-800',
		danger: 'bg-red-600 text-white hover:bg-red-700 focus-visible:outline-red-600',
		// For a button placed on a colored/dark background (e.g. a marketing CTA
		// band) — new, additive; no existing call site uses either variant.
		inverse: 'bg-white text-brand-700 hover:bg-white/90 focus-visible:outline-white',
		'outline-inverse':
			'bg-transparent text-white border border-white/40 hover:bg-white/10 focus-visible:outline-white'
	};

	const sizeClasses = {
		sm: 'px-3 py-1.5 text-sm gap-1.5',
		md: 'px-4 py-2 text-sm gap-2',
		lg: 'px-5 py-2.5 text-base gap-2'
	};

	let classes = $derived(
		[
			'inline-flex items-center justify-center rounded-lg font-medium transition-colors',
			'focus-visible:outline-2 focus-visible:outline-offset-2',
			'disabled:opacity-50 disabled:cursor-not-allowed',
			variantClasses[variant],
			sizeClasses[size],
			fullWidth ? 'w-full' : '',
			className
		].join(' ')
	);
</script>

{#if href && !disabled}
	<!-- `href` is an opaque prop forwarded from the caller — it may be an
	     internal route or an external URL, so it can't be checked against
	     SvelteKit's resolve() here. A caller linking to one of this app's own
	     routes should pass an already-resolved path. -->
	<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
	<a {href} class={classes} {...rest}>
		{@render children?.()}
	</a>
{:else}
	<button {type} disabled={disabled || loading} class={classes} {onclick} {...rest}>
		{#if loading}
			<svg class="size-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
				<path
					class="opacity-75"
					fill="currentColor"
					d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
				/>
			</svg>
		{/if}
		{@render children?.()}
	</button>
{/if}
