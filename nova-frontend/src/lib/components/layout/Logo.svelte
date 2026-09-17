<script>
	/**
	 * The NOVA brand mark. Inline (not the static favicon file) so its
	 * gradient can reference the live brand tokens from layout.css and stay
	 * in sync automatically if the palette ever changes.
	 *
	 * @type {{
	 *   variant?: 'full'|'mark',
	 *   class?: string
	 * }}
	 */
	let { variant = 'full', class: className = '' } = $props();
</script>

<span class={['inline-flex items-center gap-2', className].join(' ')}>
	<svg width="28" height="28" viewBox="0 0 32 32" fill="none" aria-hidden="true" class="shrink-0">
		<defs>
			<linearGradient
				id="nova-logo-gradient"
				x1="0"
				y1="0"
				x2="32"
				y2="32"
				gradientUnits="userSpaceOnUse"
			>
				<stop offset="0%" stop-color="var(--color-brand-500)" />
				<stop offset="100%" stop-color="var(--color-plum-700)" />
			</linearGradient>
		</defs>
		<rect width="32" height="32" rx="9" fill="url(#nova-logo-gradient)" />
		<rect x="6" y="6" width="5" height="20" rx="1" fill="white" />
		<rect x="21" y="6" width="5" height="20" rx="1" fill="white" />
		<polygon points="11,6 16,6 26,26 21,26" fill="white" />
	</svg>
	{#if variant === 'full'}
		<span class="text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-100">
			NOVA
		</span>
	{/if}
</span>
