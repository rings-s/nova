<script>
	/**
	 * Pairs with the backend's `limit`/`offset` paging (core/pagination.py).
	 * `total` is `null` on endpoints that deliberately don't count the full
	 * result set (e.g. discovery search) — hide the page count in that case.
	 * @type {{
	 *   limit: number,
	 *   offset: number,
	 *   total?: number|null,
	 *   itemCount: number,
	 *   onchange: (offset: number) => void
	 * }}
	 */
	let { limit, offset, total = null, itemCount, onchange } = $props();

	let currentPage = $derived(Math.floor(offset / limit) + 1);
	let totalPages = $derived(total !== null ? Math.max(1, Math.ceil(total / limit)) : null);
	let hasNext = $derived(total !== null ? offset + limit < total : itemCount === limit);
	let hasPrev = $derived(offset > 0);
</script>

<div class="flex items-center justify-between gap-4 text-sm text-slate-600 dark:text-slate-300">
	<p>
		{#if totalPages}
			Page {currentPage} of {totalPages}
		{:else}
			Page {currentPage}
		{/if}
	</p>
	<div class="flex gap-2">
		<button
			type="button"
			disabled={!hasPrev}
			onclick={() => onchange(Math.max(0, offset - limit))}
			class="rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-40 dark:border-slate-700"
		>
			Previous
		</button>
		<button
			type="button"
			disabled={!hasNext}
			onclick={() => onchange(offset + limit)}
			class="rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-40 dark:border-slate-700"
		>
			Next
		</button>
	</div>
</div>
