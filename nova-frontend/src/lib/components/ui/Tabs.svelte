<script>
	/**
	 * A segmented control: the options sit in a sunken track and the active
	 * one is raised onto it. Arrow keys move between tabs (WAI-ARIA tabs).
	 *
	 * @type {{
	 *   tabs: { id: string, label: string, count?: number|null }[],
	 *   active?: string,
	 *   onchange?: (id: string) => void
	 * }}
	 */
	let { tabs = [], active = $bindable(''), onchange } = $props();

	/** @param {string} id */
	function select(id) {
		active = id;
		onchange?.(id);
	}

	/** @param {KeyboardEvent} event @param {number} index */
	function onkeydown(event, index) {
		const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
		if (!step) return;
		event.preventDefault();
		const rtl = getComputedStyle(/** @type {Element} */ (event.currentTarget)).direction === 'rtl';
		const next = tabs[(index + (rtl ? -step : step) + tabs.length) % tabs.length];
		select(next.id);
		/** @type {HTMLElement|null} */ (
			/** @type {HTMLElement} */ (event.currentTarget).parentElement?.querySelector(
				`[data-tab="${next.id}"]`
			)
		)?.focus();
	}
</script>

<div
	class="inline-flex max-w-full [scrollbar-width:none] gap-1 overflow-x-auto rounded-control bg-surface-muted p-1"
	role="tablist"
>
	{#each tabs as tab, index (tab.id)}
		<button
			type="button"
			role="tab"
			data-tab={tab.id}
			aria-selected={active === tab.id}
			tabindex={active === tab.id ? 0 : -1}
			onclick={() => select(tab.id)}
			onkeydown={(event) => onkeydown(event, index)}
			class={[
				'inline-flex h-8 shrink-0 items-center gap-2 rounded-[calc(var(--radius-control)-2px)] px-3.5 text-sm font-medium whitespace-nowrap',
				'focus-ring transition-[background-color,color,box-shadow] duration-fast ease-out-premium',
				active === tab.id
					? 'bg-surface text-fg shadow-card ring-1 ring-line dark:bg-slate-700/60 dark:ring-white/5'
					: 'text-fg-muted hover:text-fg'
			].join(' ')}
		>
			{tab.label}
			{#if tab.count != null}
				<span class="rounded-full bg-surface-muted px-1.5 text-[11px] text-fg-muted tabular-nums"
					>{tab.count}</span
				>
			{/if}
		</button>
	{/each}
</div>
