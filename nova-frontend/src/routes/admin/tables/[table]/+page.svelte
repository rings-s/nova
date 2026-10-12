<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * One table's rows across every business: search, exact-match filters, sort
	 * and pages, all kept in the URL so a filtered view can be linked to (the
	 * row page links "bookings of this customer" here).
	 */
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { describeTable, listRows } from '$lib/api/admin.js';
	import { humanize, listColumns } from '$lib/admin/console.svelte.js';
	import { formatApiError } from '$lib/utils/errors.js';

	import AdminValue from '$lib/components/admin/AdminValue.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Checkbox from '$lib/components/ui/Checkbox.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';

	const LIMIT = 50;

	let table = $derived(page.params.table ?? '');
	let params = $derived(page.url.searchParams);
	let q = $derived(params.get('q') ?? '');
	let filters = $derived(params.getAll('filter'));
	let orderBy = $derived(params.get('order_by'));
	let desc = $derived(params.get('desc') === 'true');
	let offset = $derived(Math.max(0, Number(params.get('offset')) || 0));

	let detail = $state(/** @type {import('$lib/api/admin.js').AdminTableDetail|null} */ (null));
	let rows = $state(/** @type {import('$lib/api/admin.js').AdminRowsPage|null} */ (null));
	let error = $state(/** @type {string|null} */ (null));
	let showAll = $state(false);

	// What the search box holds: the URL's search until the user types.
	let search = $derived(q);
	let filterColumn = $state('');
	let filterValue = $state('');

	$effect(() => {
		const name = table;
		let cancelled = false;
		detail = null;
		error = null;
		describeTable(name)
			.then((result) => {
				if (!cancelled) detail = result;
			})
			.catch((err) => {
				if (!cancelled) error = formatApiError(err);
			});
		return () => {
			cancelled = true;
		};
	});

	$effect(() => {
		const request = { q, filters, orderBy, desc, limit: LIMIT, offset };
		const name = table;
		let cancelled = false;
		rows = null;
		listRows(name, request)
			.then((result) => {
				if (!cancelled) rows = result;
			})
			.catch((err) => {
				if (!cancelled) error = formatApiError(err);
			});
		return () => {
			cancelled = true;
		};
	});

	// The primary key first either way: its cell links to the row.
	let columns = $derived(
		!detail
			? []
			: showAll
				? [
						...detail.columns.filter((column) => column.primary_key),
						...detail.columns.filter((column) => !column.primary_key)
					]
				: listColumns(detail.columns)
	);
	let filterable = $derived(detail?.columns.filter((column) => column.filterable) ?? []);
	let chosenFilter = $derived(filterable.find((column) => column.name === filterColumn));
	let filterChoices = $derived(
		chosenFilter?.type === 'boolean'
			? [
					{ value: 'true', label: t('Yes') },
					{ value: 'false', label: t('No') }
				]
			: (chosenFilter?.choices ?? []).map((choice) => ({ value: choice, label: choice }))
	);
	let searchable = $derived(detail?.columns.some((column) => column.searchable) ?? false);

	/** @param {Record<string, string|string[]|null>} changes */
	function navigate(changes) {
		const kept = [...params].filter(([key]) => !(key in changes));
		const added = Object.entries(changes).flatMap(([key, value]) =>
			(Array.isArray(value) ? value : value ? [value] : []).map((item) => [key, item])
		);
		const query = new URLSearchParams([...kept, ...added]).toString();
		// eslint-disable-next-line svelte/no-navigation-without-resolve
		goto(`${resolve('/admin/tables/[table]', { table })}${query ? `?${query}` : ''}`, {
			keepFocus: true,
			noScroll: true
		});
	}

	/** @param {SubmitEvent} event */
	function submitSearch(event) {
		event.preventDefault();
		navigate({ q: search.trim() || null, offset: null });
	}

	/** @param {SubmitEvent} event */
	function addFilter(event) {
		event.preventDefault();
		if (!filterColumn) return;
		const rest = filters.filter((item) => !item.startsWith(`${filterColumn}:`));
		navigate({ filter: [...rest, `${filterColumn}:${filterValue.trim()}`], offset: null });
		filterValue = '';
	}

	/** @param {string} filter */
	function removeFilter(filter) {
		navigate({ filter: filters.filter((item) => item !== filter), offset: null });
	}

	/** @param {import('$lib/api/admin.js').AdminColumn} column */
	function sortBy(column) {
		const descending = orderBy === column.name ? !desc : false;
		navigate({ order_by: column.name, desc: descending ? 'true' : null, offset: null });
	}
</script>

<svelte:head><title>{humanize(table)} — {t('NOVA administration')}</title></svelte:head>

<PageHeader eyebrow={t('NOVA administration')} title={humanize(table)} subtitle={table}>
	{#snippet actions()}
		{#if rows}
			<Badge tone="neutral">{t('{count} rows', { count: rows.total })}</Badge>
		{/if}
	{/snippet}
</PageHeader>

{#if error}
	<Alert tone="error" class="mt-6">{error}</Alert>
{/if}

<Card padding="md" class="mt-2">
	<div class="flex flex-col gap-3">
		<div class="flex flex-wrap items-end gap-3">
			{#if searchable}
				<form class="flex min-w-60 flex-1 items-end gap-2" onsubmit={submitSearch}>
					<div class="flex-1">
						<Input
							type="search"
							label={t('Search')}
							placeholder={t('Text, or a pasted id')}
							maxlength="200"
							bind:value={search}
						/>
					</div>
					<Button type="submit" variant="outline">
						<Icon name="search" class="size-4" />
						{t('Search')}
					</Button>
				</form>
			{/if}

			{#if filterable.length > 0}
				<form class="flex flex-wrap items-end gap-2" onsubmit={addFilter}>
					<Select
						label={t('Filter by')}
						placeholder={t('Column')}
						options={filterable.map((column) => ({ value: column.name, label: column.name }))}
						bind:value={filterColumn}
					/>
					{#if filterChoices.length > 0}
						<Select
							label={t('Equals')}
							placeholder={t('Value')}
							required
							options={filterChoices}
							bind:value={filterValue}
						/>
					{:else}
						<Input label={t('Equals')} placeholder={t('Value')} required bind:value={filterValue} />
					{/if}
					<Button type="submit" variant="outline" disabled={!filterColumn || !filterValue.trim()}>
						<Icon name="filter" class="size-4" />
						{t('Add filter')}
					</Button>
				</form>
			{/if}
		</div>

		{#if filters.length > 0 || q}
			<div class="flex flex-wrap items-center gap-2 border-t border-line-subtle pt-3">
				{#if q}
					<button
						type="button"
						class="rounded-full focus-ring"
						onclick={() => navigate({ q: null, offset: null })}
						aria-label={t('Clear search')}
					>
						<Badge tone="accent">
							<span dir="auto">“{q}”</span>
							<Icon name="x" class="size-3" />
						</Badge>
					</button>
				{/if}
				{#each filters as filter (filter)}
					<button
						type="button"
						class="rounded-full focus-ring"
						onclick={() => removeFilter(filter)}
						aria-label={t('Remove filter {filter}', { filter })}
					>
						<Badge tone="info">
							<span class="font-mono" dir="ltr">{filter.replace(':', ' = ')}</span>
							<Icon name="x" class="size-3" />
						</Badge>
					</button>
				{/each}
			</div>
		{/if}
	</div>
</Card>

<div class="mt-4 flex justify-end">
	<Checkbox label={t('Show every column')} bind:checked={showAll} />
</div>

<Card padding="none" class="mt-2 overflow-hidden shadow-raised">
	{#if !detail || !rows}
		<div class="flex flex-col gap-2 p-4">
			{#each { length: 6 }, index (index)}
				<Skeleton class="h-8 w-full" />
			{/each}
		</div>
	{:else if rows.items.length === 0}
		<EmptyState class="py-12" title={t('No rows match')} />
	{:else}
		<div class="overflow-x-auto">
			<table class="w-full text-start text-sm">
				<thead
					class="sticky top-0 z-10 border-b border-line bg-surface-muted text-xs text-fg-muted"
				>
					<tr>
						{#each columns as column (column.name)}
							<th scope="col" class="px-3 py-2 text-start font-medium whitespace-nowrap">
								{#if column.type === 'json' || column.masked}
									<span class="font-mono">{column.name}</span>
								{:else}
									<button
										type="button"
										class="inline-flex items-center gap-1 rounded-control font-mono focus-ring hover:text-fg"
										onclick={() => sortBy(column)}
									>
										{column.name}
										{#if orderBy === column.name}
											<Icon name={desc ? 'arrow-down' : 'arrow-up'} class="size-3" />
										{/if}
									</button>
								{/if}
							</th>
						{/each}
					</tr>
				</thead>
				<tbody class="divide-y divide-line-subtle">
					{#each rows.items as row (row.id)}
						<tr class="even:bg-surface-sunken/40 hover:bg-accent-soft/40">
							{#each columns as column, index (column.name)}
								<td class="px-3 py-2 align-top">
									{#if index === 0}
										<a
											href={resolve('/admin/tables/[table]/[id]', { table, id: row.id })}
											class="rounded-control font-mono text-xs font-medium text-accent focus-ring hover:underline"
											dir="ltr"
											title={row.id}
										>
											{column.type === 'uuid'
												? `${String(row.values[column.name]).slice(0, 8)}…`
												: String(row.values[column.name] ?? row.id)}
										</a>
									{:else}
										<AdminValue value={row.values[column.name]} {column} />
									{/if}
								</td>
							{/each}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<div class="px-4 pb-4">
			<Pagination
				limit={LIMIT}
				{offset}
				total={rows.total}
				itemCount={rows.items.length}
				onchange={(next) => navigate({ offset: next ? String(next) : null })}
			/>
		</div>
	{/if}
</Card>
