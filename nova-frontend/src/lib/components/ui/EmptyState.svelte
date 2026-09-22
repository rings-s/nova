<script>
	/**
	 * @type {{
	 *   title: string,
	 *   description?: string|null,
	 *   action?: import('svelte').Snippet,
	 *   icon?: import('svelte').Snippet,
	 *   class?: string
	 * }}
	 */
	let { title, description = null, action, icon, class: className = '' } = $props();
</script>

<div
	class={`flex flex-col items-center rounded-card border border-dashed border-line-strong bg-surface-sunken/60 px-6 py-14 text-center ${className}`}
>
	<div
		class="mb-4 flex size-12 items-center justify-center rounded-card border border-line bg-surface text-fg-muted shadow-card"
	>
		{#if icon}
			{@render icon()}
		{:else}
			<svg
				class="size-6"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="1.5"
				aria-hidden="true"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					d="M3.5 13.5h4.3l1.4 2.5h5.6l1.4-2.5h4.3M5.2 6.2 3.5 13.5v4A2.5 2.5 0 0 0 6 20h12a2.5 2.5 0 0 0 2.5-2.5v-4l-1.7-7.3A2.5 2.5 0 0 0 16.4 4H7.6a2.5 2.5 0 0 0-2.4 2.2z"
				/>
			</svg>
		{/if}
	</div>
	<p class="font-semibold text-fg">{title}</p>
	{#if description}
		<p class="mt-1 max-w-sm text-sm text-fg-muted">{description}</p>
	{/if}
	{#if action}
		<div class="mt-5">{@render action()}</div>
	{/if}
</div>
