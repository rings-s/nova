<script>
	/**
	 * Shared shell for every unauthenticated auth screen: one centered card,
	 * so login/register/(future) phone-verification all read as one flow
	 * rather than each inventing its own page chrome.
	 */
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';

	let { children } = $props();
</script>

<div
	class="relative flex min-h-[calc(100dvh-57px)] items-center justify-center overflow-hidden px-4 py-12 sm:px-6"
	style="background-image: var(--gradient-soft)"
>
	<GradientBlob variant="soft" />
	<div class="w-full max-w-md">
		{@render children()}
	</div>
</div>
