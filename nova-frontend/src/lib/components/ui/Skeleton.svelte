<script>
	/**
	 * A loading placeholder shaped like the content it stands in for. Prefer
	 * it to a spinner wherever the layout is known ahead of the data, so the
	 * page doesn't jump when it arrives.
	 *
	 * @type {{ class?: string }}
	 */
	let { class: className = 'h-4 w-full' } = $props();
</script>

<div class={`animate-shimmer rounded-md bg-surface-muted ${className}`} aria-hidden="true"></div>
