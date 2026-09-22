<script>
	import Button from './Button.svelte';
	import Icon from './Icon.svelte';

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

<nav
	class="flex items-center justify-between gap-4 border-t border-line pt-4 text-sm"
	aria-label="Pagination"
>
	<p class="text-fg-muted tabular-nums">
		{#if totalPages}
			Page <span class="font-medium text-fg">{currentPage}</span> of {totalPages}
		{:else}
			Page <span class="font-medium text-fg">{currentPage}</span>
		{/if}
	</p>
	<div class="flex gap-2">
		<Button
			variant="outline"
			size="sm"
			disabled={!hasPrev}
			onclick={() => onchange(Math.max(0, offset - limit))}
		>
			<Icon name="chevron-left" class="size-4 rtl:rotate-180" />
			Previous
		</Button>
		<Button
			variant="outline"
			size="sm"
			disabled={!hasNext}
			onclick={() => onchange(offset + limit)}
		>
			Next
			<Icon name="chevron-right" class="size-4 rtl:rotate-180" />
		</Button>
	</div>
</nav>
