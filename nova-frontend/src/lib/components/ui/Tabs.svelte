<script>
	/**
	 * @type {{
	 *   tabs: { id: string, label: string }[],
	 *   active?: string,
	 *   onchange?: (id: string) => void
	 * }}
	 */
	let { tabs = [], active = $bindable(''), onchange } = $props();

	function select(id) {
		active = id;
		onchange?.(id);
	}
</script>

<div class="flex gap-1 border-b border-slate-200 dark:border-slate-800" role="tablist">
	{#each tabs as tab (tab.id)}
		<button
			type="button"
			role="tab"
			aria-selected={active === tab.id}
			onclick={() => select(tab.id)}
			class={[
				'-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors',
				active === tab.id
					? 'border-rose-600 text-rose-600'
					: 'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
			].join(' ')}
		>
			{tab.label}
		</button>
	{/each}
</div>
