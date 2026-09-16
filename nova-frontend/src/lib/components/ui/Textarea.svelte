<script>
	/**
	 * @type {{
	 *   value?: string,
	 *   label?: string|null,
	 *   placeholder?: string|null,
	 *   error?: string|null,
	 *   hint?: string|null,
	 *   required?: boolean,
	 *   disabled?: boolean,
	 *   rows?: number,
	 *   id?: string|null,
	 *   class?: string,
	 *   [key: string]: unknown
	 * }}
	 */
	let {
		value = $bindable(''),
		label = null,
		placeholder = null,
		error = null,
		hint = null,
		required = false,
		disabled = false,
		rows = 3,
		id = null,
		class: className = '',
		...rest
	} = $props();

	let areaId = $derived(id ?? `textarea-${Math.random().toString(36).slice(2, 9)}`);
</script>

<div class="flex flex-col gap-1">
	{#if label}
		<label for={areaId} class="text-sm font-medium text-slate-700 dark:text-slate-200">
			{label}
			{#if required}<span class="text-brand-600">*</span>{/if}
		</label>
	{/if}
	<textarea
		id={areaId}
		{placeholder}
		{required}
		{disabled}
		{rows}
		bind:value
		class={[
			'resize-y rounded-lg border px-3 py-2 text-sm shadow-sm transition-colors',
			'bg-white text-slate-900 placeholder:text-slate-400',
			'dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500',
			'focus:outline-2 focus:outline-offset-1',
			'disabled:cursor-not-allowed disabled:opacity-50',
			error
				? 'border-red-400 focus:outline-red-500'
				: 'border-slate-300 focus:outline-brand-500 dark:border-slate-700',
			className
		].join(' ')}
		aria-invalid={Boolean(error)}
		{...rest}></textarea>
	{#if error}
		<p class="text-sm text-red-600">{error}</p>
	{:else if hint}
		<p class="text-sm text-slate-500 dark:text-slate-400">{hint}</p>
	{/if}
</div>
