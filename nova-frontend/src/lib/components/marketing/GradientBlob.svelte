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
			class="blob-a absolute size-[28rem] opacity-70 blur-3xl"
			style="inset-block-start: -6rem; inset-inline-start: -6rem; background-image: var(--gradient-glow-1);"
		></div>
		<div
			class="blob-b absolute size-[26rem] opacity-60 blur-3xl"
			style="inset-block-end: -8rem; inset-inline-end: -6rem; background-image: var(--gradient-glow-2);"
		></div>
	{:else if variant === 'soft'}
		<div
			class="blob-centered absolute size-[32rem] opacity-40 blur-3xl"
			style="inset-block-start: 50%; inset-inline-start: 50%; margin-block-start: -16rem; margin-inline-start: -16rem; background-image: var(--gradient-glow-1);"
		></div>
	{:else}
		<div
			class="blob-c absolute size-56 opacity-50 blur-2xl"
			style="inset-block-end: -3rem; inset-inline-end: -3rem; background-image: var(--gradient-glow-2);"
		></div>
	{/if}
</div>

<style>
	/*
	 * Slow, organic drift + shape morph — the "alive" quality that separates
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
	@keyframes blob-float-a {
		0%,
		100% {
			transform: translate(0, 0) scale(1);
			border-radius: 60% 40% 30% 70% / 60% 30% 70% 40%;
		}
		50% {
			transform: translate(2rem, 3rem) scale(1.08);
			border-radius: 40% 60% 70% 30% / 50% 60% 40% 50%;
		}
	}
	@keyframes blob-float-b {
		0%,
		100% {
			transform: translate(0, 0) scale(1);
			border-radius: 40% 60% 70% 30% / 50% 60% 40% 50%;
		}
		50% {
			transform: translate(-2.5rem, -2rem) scale(1.1);
			border-radius: 55% 45% 40% 60% / 45% 55% 45% 55%;
		}
	}
	@keyframes blob-float-c {
		0%,
		100% {
			transform: scale(1);
			border-radius: 50% 50% 45% 55% / 55% 45% 55% 45%;
		}
		50% {
			transform: scale(1.08);
			border-radius: 45% 55% 55% 45% / 50% 55% 45% 50%;
		}
	}

	.blob-a {
		animation: blob-float-a 22s ease-in-out infinite;
	}
	.blob-b {
		animation: blob-float-b 26s ease-in-out infinite;
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
