<script>
	/**
	 * @type {{
	 *   variant?: 'primary'|'secondary'|'outline'|'ghost'|'danger'|'danger-ghost'|'inverse'|'outline-inverse',
	 *   size?: 'sm'|'md'|'lg'|'icon'|'icon-sm',
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

	/*
	 * One emphasis ladder: primary (brand, the page's main action) > secondary
	 * (ink) > outline > ghost. `inverse`/`outline-inverse` are the same two
	 * steps for a button on a colored or dark band.
	 */
	const variantClasses = {
		primary:
			'bg-brand-600 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.15),0_1px_2px_rgb(190_18_60/0.3)] hover:bg-brand-700',
		secondary:
			'bg-slate-900 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.1)] hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white',
		outline: 'border border-line-strong bg-surface text-fg shadow-card hover:bg-surface-muted',
		ghost: 'text-fg-secondary hover:bg-surface-muted hover:text-fg',
		danger: 'bg-red-600 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.15)] hover:bg-red-700',
		// A destructive action that isn't the row's main action (Remove, Revoke).
		'danger-ghost':
			'text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-400 dark:hover:bg-red-500/10 dark:hover:text-red-300',
		inverse: 'bg-white text-brand-700 shadow-raised hover:bg-white/90',
		'outline-inverse': 'border border-white/40 text-white hover:bg-white/10'
	};

	// Heights 32 / 40 / 48: every control in a row lines up with an Input (40).
	const sizeClasses = {
		sm: 'h-8 px-3 text-[13px] gap-1.5',
		md: 'h-10 px-4 text-sm gap-2',
		lg: 'h-12 px-6 text-[15px] gap-2',
		// Square, for an icon-only button — give it an aria-label.
		icon: 'size-10',
		'icon-sm': 'size-8'
	};

	let classes = $derived(
		[
			'relative inline-flex shrink-0 select-none items-center justify-center rounded-control font-medium whitespace-nowrap',
			'transition-[background-color,color,box-shadow,transform] duration-fast ease-out-premium active:scale-[0.98]',
			'focus-ring',
			'disabled:pointer-events-none disabled:opacity-50',
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
	<button
		{type}
		disabled={disabled || loading}
		aria-busy={loading || undefined}
		class={classes}
		{onclick}
		{...rest}
	>
		{#if loading}
			<svg class="size-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" />
				<path
					class="opacity-90"
					fill="currentColor"
					d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
				/>
			</svg>
		{/if}
		{@render children?.()}
	</button>
{/if}
