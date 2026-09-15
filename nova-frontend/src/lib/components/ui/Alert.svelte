<script>
	/**
	 * @type {{
	 *   tone?: 'info'|'success'|'warning'|'error',
	 *   title?: string|null,
	 *   dismissible?: boolean,
	 *   ondismiss?: () => void,
	 *   children?: import('svelte').Snippet,
	 *   class?: string
	 * }}
	 */
	let {
		tone = 'info',
		title = null,
		dismissible = false,
		ondismiss,
		children,
		class: className = ''
	} = $props();

	const toneClasses = {
		info: 'bg-sky-50 text-sky-800 border-sky-200 dark:bg-sky-950/40 dark:text-sky-200 dark:border-sky-900',
		success:
			'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-900',
		warning:
			'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/40 dark:text-amber-200 dark:border-amber-900',
		error:
			'bg-red-50 text-red-800 border-red-200 dark:bg-red-950/40 dark:text-red-200 dark:border-red-900'
	};
</script>

<div
	class={`flex items-start gap-3 rounded-lg border px-4 py-3 text-sm ${toneClasses[tone]} ${className}`}
	role="alert"
>
	<div class="flex-1">
		{#if title}<p class="font-medium">{title}</p>{/if}
		<div class={title ? 'mt-1' : ''}>{@render children?.()}</div>
	</div>
	{#if dismissible}
		<button
			type="button"
			onclick={ondismiss}
			class="shrink-0 rounded p-1 opacity-70 hover:opacity-100"
			aria-label="Dismiss"
		>
			<svg class="size-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
				<path
					d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 10-1.06-1.06L10 8.94 6.28 5.22z"
				/>
			</svg>
		</button>
	{/if}
</div>
