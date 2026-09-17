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
		<p class="text-xs font-semibold tracking-wide text-brand-600 uppercase dark:text-brand-400">
			{eyebrow}
		</p>
	{/if}
	<h2 class="mt-2 text-display-lg font-semibold tracking-tight text-slate-900 dark:text-slate-100">
		{title}
	</h2>
	{#if subtitle}
		<p
			class={[
				'mt-4 text-body-lg text-slate-600 dark:text-slate-400',
				align === 'center' ? 'mx-auto max-w-2xl' : 'max-w-2xl'
			].join(' ')}
		>
			{subtitle}
		</p>
	{/if}
</div>
