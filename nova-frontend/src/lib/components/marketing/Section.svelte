<script>
	/**
	 * Marketing-only vertical rhythm wrapper. Never used under /app.
	 *
	 * `padding` is a mutually-exclusive class set rather than a `class`
	 * override, deliberately — two conflicting Tailwind padding utilities on
	 * the same element (e.g. a caller's `pb-10` alongside this component's
	 * own default `py-20`) have equal specificity, so which one wins depends
	 * on Tailwind's generated stylesheet order, not source order. A prop with
	 * a fixed set of options sidesteps that entirely.
	 *
	 * @type {{
	 *   tone?: 'canvas'|'sunken'|'dark',
	 *   padding?: 'default'|'tight'|'none',
	 *   class?: string,
	 *   children?: import('svelte').Snippet
	 * }}
	 */
	let { tone = 'canvas', padding = 'default', class: className = '', children } = $props();

	const toneClasses = {
		canvas: '',
		sunken: 'bg-slate-50 dark:bg-slate-900/40',
		dark: 'text-white'
	};

	const paddingClasses = {
		default: 'py-20 sm:py-28',
		tight: 'py-10 sm:py-14',
		none: ''
	};
</script>

<section
	class={['relative overflow-hidden', paddingClasses[padding], toneClasses[tone], className].join(
		' '
	)}
	style={tone === 'dark' ? 'background-image: var(--gradient-cta)' : undefined}
>
	{@render children?.()}
</section>
