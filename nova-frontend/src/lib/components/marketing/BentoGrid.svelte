<script>
	/** @type {{ class?: string, children?: import('svelte').Snippet }} */
	let { class: className = '', children } = $props();
</script>

<div class={['grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4', className].join(' ')}>
	{@render children?.()}
</div>
