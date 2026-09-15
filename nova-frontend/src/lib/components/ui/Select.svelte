<script>
	/**
	 * @type {{
	 *   value?: string|number|null,
	 *   options: { value: string|number, label: string }[],
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
		options = [],
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

	const selectId = id ?? `select-${Math.random().toString(36).slice(2, 9)}`;
</script>

<div class="flex flex-col gap-1">
	{#if label}
		<label for={selectId} class="text-sm font-medium text-slate-700 dark:text-slate-200">
			{label}
			{#if required}<span class="text-rose-600">*</span>{/if}
		</label>
	{/if}
	<select
		id={selectId}
		{required}
		{disabled}
		bind:value
		class={[
			'rounded-lg border px-3 py-2 text-sm shadow-sm transition-colors',
			'bg-white text-slate-900 dark:bg-slate-900 dark:text-slate-100',
			'focus:outline-2 focus:outline-offset-1',
			'disabled:opacity-50 disabled:cursor-not-allowed',
			error
				? 'border-red-400 focus:outline-red-500'
				: 'border-slate-300 focus:outline-rose-500 dark:border-slate-700',
			className
		].join(' ')}
		aria-invalid={Boolean(error)}
		{...rest}
	>
		{#if placeholder}
			<option value="" disabled selected={!value}>{placeholder}</option>
		{/if}
		{#each options as option (option.value)}
			<option value={option.value}>{option.label}</option>
		{/each}
	</select>
	{#if error}
		<p class="text-sm text-red-600">{error}</p>
	{:else if hint}
		<p class="text-sm text-slate-500 dark:text-slate-400">{hint}</p>
	{/if}
</div>
