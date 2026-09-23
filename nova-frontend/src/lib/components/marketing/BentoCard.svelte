<script>
	/**
	 * A marketing feature tile: the card surface with a softer hover lift.
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
		'rounded-card border border-line bg-surface p-6 shadow-card transition-[border-color,box-shadow,transform] duration-base ease-out-premium hover:-translate-y-0.5 hover:border-line-strong hover:shadow-raised',
		span === 2 ? 'sm:col-span-2' : '',
		className
	].join(' ')}
>
	{@render children?.()}
</div>
