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

	// Per-instance gradient id: several logos can be on one page (sidebar,
	// mobile bar, footer), and a url(#id) that resolves to a copy inside a
	// display:none ancestor paints nothing.
	const uid = $props.id();
	const gradientId = `nova-logo-gradient-${uid}`;
</script>

<span class={['inline-flex items-center gap-2', className].join(' ')}>
	<svg width="28" height="28" viewBox="0 0 32 32" fill="none" aria-hidden="true" class="shrink-0">
		<defs>
			<linearGradient id={gradientId} x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
				<stop offset="0%" stop-color="var(--color-brand-500)" />
				<stop offset="100%" stop-color="var(--color-plum-700)" />
			</linearGradient>
		</defs>
		<rect width="32" height="32" rx="9" fill={`url(#${gradientId})`} />
		<rect x="6" y="6" width="5" height="20" rx="1" fill="white" />
		<rect x="21" y="6" width="5" height="20" rx="1" fill="white" />
		<polygon points="11,6 16,6 26,26 21,26" fill="white" />
	</svg>
	{#if variant === 'full'}
		<span class="text-lg font-semibold tracking-tight text-fg"> NOVA </span>
	{/if}
</span>
