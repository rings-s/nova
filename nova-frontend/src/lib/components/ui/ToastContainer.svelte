<script>
	/**
	 * Mount once in the root layout: `<ToastContainer />`. Everything else
	 * pushes to it via `$lib/stores/toast.svelte.js` — `toastStore.success(...)`.
	 */
	import { toastStore } from '../../stores/toast.svelte.js';

	const toneClasses = {
		info: 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900',
		success: 'bg-emerald-600 text-white',
		error: 'bg-red-600 text-white'
	};
</script>

<div
	class="fixed inset-x-0 bottom-4 z-[100] flex flex-col items-center gap-2 px-4 sm:items-end sm:pe-6"
>
	{#each toastStore.all as toast (toast.id)}
		<div
			class={`flex w-full max-w-sm items-start justify-between gap-3 rounded-lg px-4 py-3 text-sm shadow-lg ${toneClasses[toast.type]}`}
			role="status"
		>
			<span class="flex-1">{toast.message}</span>
			<button
				type="button"
				onclick={() => toastStore.dismiss(toast.id)}
				class="shrink-0 opacity-80 hover:opacity-100"
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
