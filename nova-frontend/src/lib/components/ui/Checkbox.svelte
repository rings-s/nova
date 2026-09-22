<script>
	/**
	 * @type {{
	 *   checked?: boolean,
	 *   label?: string|null,
	 *   disabled?: boolean,
	 *   id?: string|null,
	 *   class?: string,
	 *   [key: string]: unknown
	 * }}
	 */
	let {
		checked = $bindable(false),
		label = null,
		disabled = false,
		id = null,
		class: className = '',
		...rest
	} = $props();

	let boxId = $derived(id ?? `checkbox-${Math.random().toString(36).slice(2, 9)}`);
</script>

<label
	for={boxId}
	class="inline-flex cursor-pointer items-center gap-2.5 text-sm text-fg-secondary select-none has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60"
>
	<input
		id={boxId}
		type="checkbox"
		{disabled}
		bind:checked
		class={`size-4 rounded-[5px] border-line-strong bg-surface text-brand-600 shadow-card transition-colors focus:ring-2 focus:ring-brand-500/30 focus:ring-offset-0 ${className}`}
		{...rest}
	/>
	{#if label}<span>{label}</span>{/if}
</label>
