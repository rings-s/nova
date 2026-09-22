<script>
	import { iconButton } from './styles.js';

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
		info: 'border-sky-200 bg-sky-50/70 text-sky-900 dark:border-sky-500/20 dark:bg-sky-500/10 dark:text-sky-100',
		success:
			'border-emerald-200 bg-emerald-50/70 text-emerald-900 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-100',
		warning:
			'border-amber-200 bg-amber-50/70 text-amber-900 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-100',
		error:
			'border-red-200 bg-red-50/70 text-red-900 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-100'
	};

	const iconClasses = {
		info: 'text-sky-500',
		success: 'text-emerald-500',
		warning: 'text-amber-500',
		error: 'text-red-500'
	};

	// 20px solid glyphs: info circle, check circle, triangle, x circle.
	const glyphs = {
		info: 'M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.25v2.75a.75.75 0 001.5 0V9.75A.75.75 0 0010 9H9z',
		success:
			'M10 18a8 8 0 100-16 8 8 0 000 16zm3.86-9.81a.75.75 0 00-1.22-.88l-3.24 4.53-1.62-1.62a.75.75 0 10-1.06 1.06l2.25 2.25a.75.75 0 001.14-.1l3.75-5.24z',
		warning:
			'M8.49 2.87c.67-1.16 2.35-1.16 3.02 0l6.28 10.88c.67 1.16-.17 2.62-1.51 2.62H3.72c-1.34 0-2.18-1.46-1.51-2.62L8.49 2.87zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 8a1 1 0 100-2 1 1 0 000 2z',
		error:
			'M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z'
	};
</script>

<div
	class={`flex items-start gap-3 rounded-card border px-4 py-3 text-sm ${toneClasses[tone]} ${className}`}
	role={tone === 'error' || tone === 'warning' ? 'alert' : 'status'}
>
	<svg
		class={`mt-px size-5 shrink-0 ${iconClasses[tone]}`}
		viewBox="0 0 20 20"
		fill="currentColor"
		aria-hidden="true"
	>
		<path fill-rule="evenodd" clip-rule="evenodd" d={glyphs[tone]} />
	</svg>
	<div class="min-w-0 flex-1 leading-relaxed">
		{#if title}<p class="font-semibold">{title}</p>{/if}
		<div class={title ? 'mt-0.5 opacity-90' : ''}>{@render children?.()}</div>
	</div>
	{#if dismissible}
		<button
			type="button"
			onclick={ondismiss}
			class={`${iconButton} -me-1.5 -mt-0.5 size-7 text-current opacity-60 hover:bg-black/5 hover:text-current hover:opacity-100 dark:hover:bg-white/10`}
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
