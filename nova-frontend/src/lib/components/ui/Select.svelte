<script>
	import { fieldBase, fieldBorder, fieldLabel, fieldHint, fieldError } from './styles.js';

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

	let selectId = $derived(id ?? `select-${Math.random().toString(36).slice(2, 9)}`);
</script>

<div class="flex flex-col gap-1.5">
	{#if label}
		<label for={selectId} class={fieldLabel}>
			{label}
			{#if required}<span class="text-brand-600" aria-hidden="true">*</span>{/if}
		</label>
	{/if}
	<select
		id={selectId}
		{required}
		{disabled}
		bind:value
		class={[fieldBase, 'h-10 pe-9', fieldBorder(Boolean(error)), className].join(' ')}
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
		<p class={fieldError}>{error}</p>
	{:else if hint}
		<p class={fieldHint}>{hint}</p>
	{/if}
</div>
