<script>
	/**
	 * @type {{
	 *   eyebrow?: string,
	 *   title: string,
	 *   subtitle?: string,
	 *   align?: 'start'|'center',
	 *   class?: string
	 * }}
	 */
	let { eyebrow, title, subtitle, align = 'start', class: className = '' } = $props();
</script>

<div class={[align === 'center' ? 'text-center' : 'text-start', className].join(' ')}>
	{#if eyebrow}
		<p class="text-xs font-semibold tracking-wider text-accent uppercase">
			{eyebrow}
		</p>
	{/if}
	<h2 class="mt-3 text-display-lg font-semibold tracking-tight text-fg">
		{title}
	</h2>
	{#if subtitle}
		<p
			class={[
				'mt-4 text-body-lg text-fg-muted',
				align === 'center' ? 'mx-auto max-w-2xl' : 'max-w-2xl'
			].join(' ')}
		>
			{subtitle}
		</p>
	{/if}
</div>
