<script>
	/**
	 * A read-only rating: five stars filled to the average (partial stars
	 * included), the number, and how many ratings it rests on. An unrated
	 * business says so instead of showing five empty stars, which would read
	 * as a bad score.
	 *
	 * @type {{
	 *   average: number|null,
	 *   count?: number,
	 *   size?: 'sm'|'md'|'lg',
	 *   compact?: boolean,
	 *   showCount?: boolean,
	 *   class?: string
	 * }}
	 */
	let {
		average,
		count = 0,
		size = 'md',
		compact = false,
		showCount = true,
		class: className = ''
	} = $props();

	const starSize = { sm: 'size-3.5', md: 'size-4', lg: 'size-5' };
	const textSize = { sm: 'text-xs', md: 'text-sm', lg: 'text-base' };

	const STAR = 'M10 1.8l2.47 5.01 5.53.8-4 3.9.94 5.5L10 14.4l-4.94 2.6.94-5.5-4-3.9 5.53-.8z';

	/** Fill fraction of star `i` (0-based) for this average. @param {number} i */
	function fill(i) {
		return Math.max(0, Math.min(1, (average ?? 0) - i));
	}

	let label = $derived(
		average == null
			? 'Not rated yet'
			: `Rated ${average.toFixed(1)} out of 5 from ${count} ${count === 1 ? 'rating' : 'ratings'}`
	);
</script>

{#if average == null}
	<span class={`inline-flex items-center gap-1 text-fg-subtle ${textSize[size]} ${className}`}>
		<svg
			class={starSize[size]}
			viewBox="0 0 20 20"
			fill="none"
			stroke="currentColor"
			stroke-width="1.5"
			aria-hidden="true"
		>
			<path d={STAR} stroke-linejoin="round" />
		</svg>
		New
	</span>
{:else}
	<span
		class={`inline-flex items-center gap-1.5 ${textSize[size]} ${className}`}
		role="img"
		aria-label={label}
		title={label}
	>
		{#if compact}
			<svg
				class={`${starSize[size]} text-amber-400`}
				viewBox="0 0 20 20"
				fill="currentColor"
				aria-hidden="true"
			>
				<path d={STAR} />
			</svg>
		{:else}
			<span class="inline-flex" aria-hidden="true">
				{#each [0, 1, 2, 3, 4] as i (i)}
					<span class={`relative ${starSize[size]}`}>
						<svg
							class="absolute inset-0 size-full text-line-strong"
							viewBox="0 0 20 20"
							fill="currentColor"
						>
							<path d={STAR} />
						</svg>
						<span
							class="absolute inset-y-0 start-0 overflow-hidden"
							style={`width: ${fill(i) * 100}%`}
						>
							<svg
								class={`${starSize[size]} text-amber-400`}
								viewBox="0 0 20 20"
								fill="currentColor"
							>
								<path d={STAR} />
							</svg>
						</span>
					</span>
				{/each}
			</span>
		{/if}
		<span class="font-semibold text-fg tabular-nums" aria-hidden="true">{average.toFixed(1)}</span>
		{#if showCount}
			<span class="text-fg-muted tabular-nums" aria-hidden="true">({count})</span>
		{/if}
	</span>
{/if}
