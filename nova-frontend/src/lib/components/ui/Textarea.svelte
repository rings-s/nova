<script>
	import { fieldBase, fieldBorder, fieldLabel, fieldHint, fieldError } from './styles.js';

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

<div class="flex flex-col gap-1.5">
	{#if label}
		<label for={areaId} class={fieldLabel}>
			{label}
			{#if required}<span class="text-brand-600" aria-hidden="true">*</span>{/if}
		</label>
	{/if}
	<textarea
		id={areaId}
		{placeholder}
		{required}
		{disabled}
		{rows}
		bind:value
		class={[fieldBase, 'min-h-20 resize-y py-2.5', fieldBorder(Boolean(error)), className].join(
			' '
		)}
		aria-invalid={Boolean(error)}
		{...rest}></textarea>
	{#if error}
		<p class={fieldError}>{error}</p>
	{:else if hint}
		<p class={fieldHint}>{hint}</p>
	{/if}
</div>
