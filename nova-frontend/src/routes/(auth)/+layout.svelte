<script>
	/**
	 * Shared shell for unauthenticated auth screens.
	 *
	 * Keeps login, registration, and future verification screens
	 * visually consistent while leaving each screen responsible
	 * only for its own card content.
	 */
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';

	let { children } = $props();
</script>

<div
	class="relative flex min-h-[calc(100dvh-57px)] flex-col items-center justify-center overflow-hidden bg-slate-50 px-4 py-10 sm:px-6 sm:py-12 dark:bg-slate-950"
>
	<GradientBlob variant="hero" />

	<div class="relative z-10 w-full max-w-md">
		{@render children()}
	</div>
</div>
