<script>
	import { iconButton } from './styles.js';

	/**
	 * @type {{
	 *   open?: boolean,
	 *   title?: string|null,
	 *   description?: string|null,
	 *   size?: 'sm'|'md'|'lg',
	 *   onclose?: () => void,
	 *   children?: import('svelte').Snippet,
	 *   footer?: import('svelte').Snippet
	 * }}
	 */
	let {
		open = $bindable(false),
		title = null,
		description = null,
		size = 'md',
		onclose,
		children,
		footer
	} = $props();

	const sizeClasses = { sm: 'sm:max-w-sm', md: 'sm:max-w-lg', lg: 'sm:max-w-2xl' };

	function close() {
		open = false;
		onclose?.();
	}

	/** @param {KeyboardEvent} event */
	function handleKeydown(event) {
		if (event.key === 'Escape') close();
	}

	// Lock page scroll while open so the backdrop doesn't scroll underneath.
	$effect(() => {
		if (!open) return;
		const previous = document.body.style.overflow;
		document.body.style.overflow = 'hidden';
		return () => {
			document.body.style.overflow = previous;
		};
	});
</script>

<svelte:window onkeydown={open ? handleKeydown : undefined} />

{#if open}
	<div class="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6">
		<div
			class="absolute inset-0 animate-fade-in bg-slate-950/40 backdrop-blur-[2px] dark:bg-slate-950/70"
			onclick={close}
			role="presentation"
		></div>
		<div
			role="dialog"
			aria-modal="true"
			aria-label={title ?? undefined}
			class={`relative z-10 flex max-h-[92dvh] w-full animate-scale-in flex-col rounded-t-panel border border-line bg-surface shadow-overlay sm:rounded-panel ${sizeClasses[size]}`}
		>
			<div class="flex items-start justify-between gap-4 px-6 pt-5 pb-4">
				<div class="min-w-0">
					<h2 class="text-lg font-semibold tracking-tight text-fg">{title}</h2>
					{#if description}<p class="mt-1 text-sm text-fg-muted">{description}</p>{/if}
				</div>
				<button
					type="button"
					onclick={close}
					class={`${iconButton} -me-2 size-8`}
					aria-label="Close"
				>
					<svg class="size-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
						<path
							d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 10-1.06-1.06L10 8.94 6.28 5.22z"
						/>
					</svg>
				</button>
			</div>
			<div class="min-h-0 flex-1 overflow-y-auto px-6 pb-6">
				{@render children?.()}
			</div>
			{#if footer}
				<div
					class="flex flex-col-reverse gap-2 rounded-b-panel border-t border-line bg-surface-sunken px-6 py-4 sm:flex-row sm:justify-end"
				>
					{@render footer()}
				</div>
			{/if}
		</div>
	</div>
{/if}
