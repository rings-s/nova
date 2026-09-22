<script>
	import { fieldBase, fieldBorder, fieldLabel, fieldHint, fieldError } from './styles.js';

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

<div class="flex flex-col gap-1.5">
	{#if label}
		<label for={inputId} class={fieldLabel}>
			{label}
			{#if required}<span class="text-brand-600" aria-hidden="true">*</span>{/if}
		</label>
	{/if}
	<input
		id={inputId}
		{type}
		{placeholder}
		{required}
		{disabled}
		bind:value
		class={[fieldBase, 'h-10', fieldBorder(Boolean(error)), className].join(' ')}
		aria-invalid={Boolean(error)}
		aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
		{...rest}
	/>
	{#if error}
		<p id="{inputId}-error" class={fieldError}>{error}</p>
	{:else if hint}
		<p id="{inputId}-hint" class={fieldHint}>{hint}</p>
	{/if}
</div>
