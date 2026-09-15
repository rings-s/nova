<script>
	/**
	 * @type {{
	 *   open?: boolean,
	 *   title?: string|null,
	 *   onclose?: () => void,
	 *   children?: import('svelte').Snippet,
	 *   footer?: import('svelte').Snippet
	 * }}
	 */
	let { open = $bindable(false), title = null, onclose, children, footer } = $props();

	function close() {
		open = false;
		onclose?.();
	}

	function handleKeydown(event) {
		if (event.key === 'Escape') close();
	}
</script>

<svelte:window onkeydown={open ? handleKeydown : undefined} />

{#if open}
	<div class="fixed inset-0 z-50 flex items-center justify-center p-4">
		<div
			class="absolute inset-0 bg-slate-950/50"
			onclick={close}
			role="presentation"
		></div>
		<div
			role="dialog"
			aria-modal="true"
			aria-label={title ?? undefined}
			class="relative z-10 w-full max-w-lg rounded-xl bg-white shadow-xl dark:bg-slate-900"
		>
			<div class="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-800">
				<h2 class="text-base font-semibold text-slate-900 dark:text-slate-100">{title}</h2>
				<button
					type="button"
					onclick={close}
					class="rounded p-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
					aria-label="Close"
				>
					<svg class="size-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
						<path
							d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 10-1.06-1.06L10 8.94 6.28 5.22z"
						/>
					</svg>
				</button>
			</div>
			<div class="max-h-[70vh] overflow-y-auto px-5 py-4">
				{@render children?.()}
			</div>
			{#if footer}
				<div class="flex justify-end gap-2 border-t border-slate-200 px-5 py-4 dark:border-slate-800">
					{@render footer()}
				</div>
			{/if}
		</div>
	</div>
{/if}
