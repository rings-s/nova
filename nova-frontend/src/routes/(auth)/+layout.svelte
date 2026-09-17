<script>
	/**
	 * Shared shell for every unauthenticated auth screen: one centered card,
	 * so login/register/(future) phone-verification all read as one flow
	 * rather than each inventing its own page chrome.
	 */
	import GradientBlob from '$lib/components/marketing/GradientBlob.svelte';
<<<<<<< HEAD
	import Icon from '$lib/components/ui/Icon.svelte';
=======
>>>>>>> 52cf860 (the clean about page design)
	let { children } = $props();
</script>

<div
	class="relative flex min-h-[calc(100dvh-57px)] flex-col items-center justify-center overflow-hidden px-4 py-12 sm:px-6"
	style="background-image: var(--gradient-soft)"
>
	<GradientBlob variant="hero" />

<<<<<<< HEAD
	<!-- Auth Shell Container -->
=======
>>>>>>> 52cf860 (the clean about page design)
	<div class="relative z-10 w-full max-w-md">
		{@render children()}

		<!-- Regulatory & Trust Footer -->
		<div class="mt-6 flex flex-wrap items-center justify-center gap-3 text-center text-[11px] text-slate-500 dark:text-slate-400">
			<span class="flex items-center gap-1">
				<Icon name="shield-check" class="size-3.5 text-emerald-600 dark:text-emerald-400" />
				<span>Moyasar PCI-DSS Level 1</span>
			</span>
			<span>·</span>
			<span>ZATCA Phase 2 E-Invoice</span>
			<span>·</span>
			<span>Saudi PDPL Compliant</span>
		</div>
	</div>
</div>
