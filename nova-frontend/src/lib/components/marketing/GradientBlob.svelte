<script>
	/**
	 * Purely decorative abstract gradient composition — the hero/section
	 * visual language in place of photography or video. Render inside a
	 * `position: relative` ancestor; this positions itself absolutely and
	 * never intercepts pointer events.
	 *
	 * @type {{ variant?: 'hero'|'soft'|'corner', class?: string }}
	 */
	let { variant = 'hero', class: className = '' } = $props();
</script>

<div
	class={['pointer-events-none absolute inset-0 -z-10 overflow-hidden', className].join(' ')}
	aria-hidden="true"
>
	{#if variant === 'hero'}
		<div
			class="blob-a absolute size-[40rem]"
			style="inset-block-start: -4rem; inset-inline-start: -16rem; background-image: var(--gradient-glow-1);"
		></div>
		<div
			class="blob-b absolute size-[38rem]"
			style="inset-block-end: -6rem; inset-inline-end: -16rem; background-image: var(--gradient-glow-2);"
		></div>
	{:else if variant === 'soft'}
		<div
			class="blob-centered absolute size-[36rem] opacity-70"
			style="inset-block-start: 50%; inset-inline-start: 50%; margin-block-start: -16rem; margin-inline-start: -16rem; background-image: var(--gradient-glow-1);"
		></div>
	{:else}
		<div
			class="blob-c absolute size-80"
			style="inset-block-end: -8rem; inset-inline-end: -8rem; background-image: var(--gradient-glow-2);"
		></div>
	{/if}
</div>

<style>
	/*
	 * Slow, organic drift — the "alive" quality that separates
	 * an abstract gradient from a static background image. Kept subtle (small
	 * translate distances, long durations) so it reads as ambient motion, not
	 * a distraction behind hero copy.
	 *
	 * Animates the single `transform` property (not the newer standalone
	 * `translate`/`scale`/`rotate` properties, which Safari only supports
	 * from 16.4 — silently no-op on anything older, which is exactly the
	 * "animation doesn't do anything" failure this avoids). `.blob-centered`
	 * gets its centering baked into the same `transform` value at every
	 * keyframe stop instead of relying on the element's inline `style`,
	 * since a keyframe's `transform` always replaces the inline one rather
	 * than composing with it.
	 */
	/*
	 * Four stops on a closed loop, so the path curves instead of reversing at
	 * two endpoints; with `ease-in-out` per segment, speed never jumps.
	 */
	@keyframes blob-float-a {
		0%,
		100% {
			transform: translate3d(0, 0, 0) scale(1);
		}
		25% {
			transform: translate3d(1.5rem, 1rem, 0) scale(1.03);
		}
		50% {
			transform: translate3d(2rem, 3rem, 0) scale(1.06);
		}
		75% {
			transform: translate3d(0.5rem, 2rem, 0) scale(1.03);
		}
	}
	@keyframes blob-float-b {
		0%,
		100% {
			transform: translate3d(0, 0, 0) scale(1);
		}
		25% {
			transform: translate3d(-1rem, -1.5rem, 0) scale(1.03);
		}
		50% {
			transform: translate3d(-2.5rem, -2rem, 0) scale(1.06);
		}
		75% {
			transform: translate3d(-1.5rem, -0.5rem, 0) scale(1.03);
		}
	}
	@keyframes blob-float-c {
		0%,
		100% {
			transform: scale(1);
		}
		50% {
			transform: scale(1.06);
		}
	}

	/*
	 * No `filter: blur()`: the gradients already fade to transparent, and a
	 * blur on a 40rem layer is re-rasterised on every frame of the drift.
	 * `will-change` keeps each blob on its own compositor layer instead.
	 */
	.blob-a,
	.blob-b,
	.blob-c,
	.blob-centered {
		will-change: transform;
	}
	.blob-a {
		animation: blob-float-a 24s ease-in-out infinite;
	}
	.blob-b {
		animation: blob-float-b 28s ease-in-out infinite;
	}
	.blob-c,
	.blob-centered {
		animation: blob-float-c 20s ease-in-out infinite;
	}

	@media (prefers-reduced-motion: reduce) {
		.blob-a,
		.blob-b,
		.blob-c,
		.blob-centered {
			animation: none;
		}
	}
</style>
