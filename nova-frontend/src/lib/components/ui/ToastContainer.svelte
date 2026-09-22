<script>
	/**
	 * Mount once in the root layout: `<ToastContainer />`. Everything else
	 * pushes to it via `$lib/stores/toast.svelte.js` — `toastStore.success(...)`.
	 */
	import { toastStore } from '../../stores/toast.svelte.js';
	import { iconButton } from './styles.js';

	const iconClasses = {
		info: 'text-sky-500',
		success: 'text-emerald-500',
		error: 'text-red-500'
	};

	const glyphs = {
		info: 'M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.25v2.75a.75.75 0 001.5 0V9.75A.75.75 0 0010 9H9z',
		success:
			'M10 18a8 8 0 100-16 8 8 0 000 16zm3.86-9.81a.75.75 0 00-1.22-.88l-3.24 4.53-1.62-1.62a.75.75 0 10-1.06 1.06l2.25 2.25a.75.75 0 001.14-.1l3.75-5.24z',
		error:
			'M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z'
	};
</script>

<div
	class="pointer-events-none fixed inset-x-0 bottom-4 z-[100] flex flex-col items-center gap-2 px-4 sm:items-end sm:pe-6"
>
	{#each toastStore.all as toast (toast.id)}
		<div
			class="pointer-events-auto flex w-full max-w-sm animate-slide-up items-start gap-3 rounded-card border border-line bg-surface px-4 py-3 text-sm text-fg shadow-overlay"
			role="status"
		>
			<svg
				class={`mt-px size-5 shrink-0 ${iconClasses[toast.type]}`}
				viewBox="0 0 20 20"
				fill="currentColor"
				aria-hidden="true"
			>
				<path fill-rule="evenodd" clip-rule="evenodd" d={glyphs[toast.type]} />
			</svg>
			<span class="flex-1 leading-relaxed">{toast.message}</span>
			<button
				type="button"
				onclick={() => toastStore.dismiss(toast.id)}
				class={`${iconButton} -me-1.5 -mt-0.5 size-7`}
				aria-label="Dismiss"
			>
				<svg class="size-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
					<path
						d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 10-1.06-1.06L10 8.94 6.28 5.22z"
					/>
				</svg>
			</button>
		</div>
	{/each}
</div>
