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

	const boxId = id ?? `checkbox-${Math.random().toString(36).slice(2, 9)}`;
</script>

<label for={boxId} class="inline-flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200 select-none">
	<input
		id={boxId}
		type="checkbox"
		{disabled}
		bind:checked
		class={`size-4 rounded border-slate-300 text-rose-600 focus:ring-rose-500 dark:border-slate-700 ${className}`}
		{...rest}
	/>
	{#if label}<span>{label}</span>{/if}
</label>
