<script>
	/**
	 * A marketing-only feature tile. Deliberately its own surface rather than
	 * `ui/Card.svelte` — its larger radius and hover-lift are part of the
	 * bespoke marketing look and must never cascade into /app, which reuses
	 * `ui/Card.svelte` directly.
	 *
	 * @type {{
	 *   span?: 1|2,
	 *   class?: string,
	 *   children?: import('svelte').Snippet
	 * }}
	 */
	let { span = 1, class: className = '', children } = $props();
</script>

<div
	class={[
		'rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition-shadow duration-200 hover:shadow-xl dark:border-slate-800 dark:bg-slate-900',
		span === 2 ? 'sm:col-span-2' : '',
		className
	].join(' ')}
>
	{@render children?.()}
</div>
