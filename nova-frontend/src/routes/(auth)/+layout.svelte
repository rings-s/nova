<script>
	/**
	 * Shared shell for every unauthenticated auth screen: one centered card,
	 * so login/register/(future) phone-verification all read as one flow
	 * rather than each inventing its own page chrome.
	 */
	let { children } = $props();
</script>

<div class="flex min-h-[calc(100dvh-57px)] items-center justify-center px-4 py-12 sm:px-6">
	<div class="w-full max-w-md">
		{@render children()}
	</div>
</div>
