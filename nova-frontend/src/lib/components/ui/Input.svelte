<script>
	/**
	 * @type {{
	 *   value?: string|number|null,
	 *   type?: string,
	 *   label?: string|null,
	 *   placeholder?: string|null,
	 *   error?: string|null,
	 *   hint?: string|null,
	 *   required?: boolean,
	 *   disabled?: boolean,
	 *   id?: string|null,
	 *   class?: string,
	 *   [key: string]: unknown
	 * }}
	 */
	let {
		value = $bindable(''),
		type = 'text',
		label = null,
		placeholder = null,
		error = null,
		hint = null,
		required = false,
		disabled = false,
		id = null,
		class: className = '',
		...rest
	} = $props();

	let inputId = $derived(id ?? `input-${Math.random().toString(36).slice(2, 9)}`);
</script>

<div class="flex flex-col gap-1">
	{#if label}
		<label for={inputId} class="text-sm font-medium text-slate-700 dark:text-slate-200">
			{label}
			{#if required}<span class="text-brand-600">*</span>{/if}
		</label>
	{/if}
	<input
		id={inputId}
		{type}
		{placeholder}
		{required}
		{disabled}
		bind:value
		class={[
			'rounded-lg border px-3 py-2 text-sm shadow-sm transition-colors',
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
		aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
		{...rest}
	/>
	{#if error}
		<p id="{inputId}-error" class="text-sm text-red-600">{error}</p>
	{:else if hint}
		<p id="{inputId}-hint" class="text-sm text-slate-500 dark:text-slate-400">{hint}</p>
	{/if}
</div>
