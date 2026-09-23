<script>
	/**
	 * Picking 1–5 stars. A radio group underneath, so it works with the
	 * keyboard (arrow keys move between stars) and a screen reader announces
	 * "3 stars, 3 of 5" like any other choice.
	 *
	 * @type {{ value?: number, name?: string, label?: string }}
	 */
	let { value = $bindable(0), name = 'rating', label = 'Your rating' } = $props();

	let hover = $state(0);
	let shown = $derived(hover || value);

	const words = ['', 'Poor', 'Fair', 'Good', 'Very good', 'Excellent'];
	const STAR = 'M10 1.8l2.47 5.01 5.53.8-4 3.9.94 5.5L10 14.4l-4.94 2.6.94-5.5-4-3.9 5.53-.8z';
</script>

<fieldset>
	<legend class="mb-2 text-sm font-medium text-fg-secondary">{label}</legend>
	<div class="flex items-center gap-3">
		<div class="flex" role="presentation" onmouseleave={() => (hover = 0)}>
			{#each [1, 2, 3, 4, 5] as star (star)}
				<label
					class="cursor-pointer rounded-control p-1 transition-transform duration-fast hover:scale-110 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand-500"
					onmouseenter={() => (hover = star)}
				>
					<input type="radio" {name} value={star} bind:group={value} class="sr-only" />
					<svg
						class={`size-8 transition-colors duration-fast ${star <= shown ? 'text-amber-400' : 'text-line-strong'}`}
						viewBox="0 0 20 20"
						fill="currentColor"
						aria-hidden="true"
					>
						<path d={STAR} />
					</svg>
					<span class="sr-only">{star} {star === 1 ? 'star' : 'stars'}</span>
				</label>
			{/each}
		</div>
		<span class="text-sm font-medium text-fg-muted" aria-live="polite">{words[shown] ?? ''}</span>
	</div>
</fieldset>
