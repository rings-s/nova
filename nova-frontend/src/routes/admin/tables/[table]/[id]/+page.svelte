<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * One row, every field, with links to the rows it points at and the rows
	 * that point at it, and the curated actions its table offers. An action runs
	 * through the module that owns the row (the API's `run_action`); there is no
	 * generic edit.
	 */
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { describeTable, getRow, runAction } from '$lib/api/admin.js';
	import { humanize } from '$lib/admin/console.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { formatApiError } from '$lib/utils/errors.js';

	import AdminValue from '$lib/components/admin/AdminValue.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Textarea from '$lib/components/ui/Textarea.svelte';

	let table = $derived(page.params.table ?? '');
	let id = $derived(page.params.id ?? '');

	let detail = $state(/** @type {import('$lib/api/admin.js').AdminTableDetail|null} */ (null));
	let row = $state(/** @type {import('$lib/api/admin.js').AdminRow|null} */ (null));
	let error = $state(/** @type {string|null} */ (null));

	/** The action awaiting confirmation, and its reason. */
	let pending = $state(/** @type {import('$lib/api/admin.js').AdminAction|null} */ (null));
	let reason = $state('');
	let running = $state(false);
	let actionError = $state(/** @type {string|null} */ (null));

	$effect(() => {
		const name = table;
		const rowId = id;
		let cancelled = false;
		detail = null;
		row = null;
		error = null;
		Promise.all([describeTable(name), getRow(name, rowId)])
			.then(([description, found]) => {
				if (cancelled) return;
				detail = description;
				row = found;
			})
			.catch((err) => {
				if (!cancelled) error = formatApiError(err);
			});
		return () => {
			cancelled = true;
		};
	});

	/** Related rows can be listed by this row's id when its key is one `id` column. */
	let related = $derived(
		detail && detail.primary_key.length === 1 && detail.primary_key[0] === 'id'
			? detail.related
			: []
	);

	/** @param {import('$lib/api/admin.js').AdminAction} action */
	function ask(action) {
		pending = action;
		reason = '';
		actionError = null;
	}

	/** @param {SubmitEvent} event */
	async function confirm(event) {
		event.preventDefault();
		if (!pending) return;
		running = true;
		actionError = null;
		try {
			row = await runAction(table, id, pending.name, { reason: reason.trim() || null });
			toastStore.success(t('Done: {action}.', { action: t(pending.label) }));
			pending = null;
		} catch (err) {
			actionError = formatApiError(err);
		} finally {
			running = false;
		}
	}

	/** @param {string} relatedTable @param {string} column */
	function relatedHref(relatedTable, column) {
		const query = new URLSearchParams({ filter: `${column}:${id}` });
		return `${resolve('/admin/tables/[table]', { table: relatedTable })}?${query}`;
	}
</script>

<svelte:head
	><title>{humanize(table)} · {id.slice(0, 8)} — {t('NOVA administration')}</title></svelte:head
>

<a
	href={resolve('/admin/tables/[table]', { table })}
	class="mb-4 inline-flex items-center gap-1.5 rounded-control text-sm font-medium text-accent focus-ring hover:underline"
>
	<Icon name="chevron-left" class="size-4 rtl:rotate-180" />
	{humanize(table)}
</a>
<PageHeader eyebrow={t('NOVA administration')} title={humanize(table)} subtitle={id} />

{#if error}
	<Alert tone="error" class="mt-6">{error}</Alert>
{:else if !detail || !row}
	<div class="mt-2 flex flex-col gap-2 rounded-card border border-line bg-surface p-5">
		{#each { length: 8 }, index (index)}
			<Skeleton class="h-8 w-full" />
		{/each}
	</div>
{:else}
	<div class="mt-2 grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_18rem]">
		<Card padding="none" class="overflow-hidden shadow-raised">
			<div
				class="flex items-center justify-between gap-3 border-b border-line bg-surface-muted px-5 py-3"
			>
				<h2 class="text-sm font-semibold text-fg">{t('Record details')}</h2>
				<span class="font-mono text-[11px] text-fg-subtle">{detail.columns.length}</span>
			</div>
			<dl class="divide-y divide-line-subtle">
				{#each detail.columns as column (column.name)}
					<div class="grid gap-1.5 px-5 py-3 sm:grid-cols-[12rem_minmax(0,1fr)] sm:gap-5">
						<dt class="pt-0.5 font-mono text-[11px] text-fg-muted" dir="ltr">
							{column.name}
							{#if column.references}
								<span class="mt-0.5 block text-[10px] text-fg-subtle">→ {column.references}</span>
							{/if}
						</dt>
						<dd class="min-w-0 rounded-control bg-surface-sunken/50 px-2.5 py-1.5 text-sm text-fg">
							<AdminValue value={row.values[column.name]} {column} full />
						</dd>
					</div>
				{/each}
			</dl>
		</Card>

		<div class="flex flex-col gap-6">
			{#if row.actions.length > 0}
				<Card padding="md" class="shadow-card">
					<div class="flex items-center gap-2">
						<span
							class="flex size-8 items-center justify-center rounded-control bg-accent-soft text-accent"
						>
							<Icon name="settings" class="size-4" />
						</span>
						<h2 class="text-sm font-semibold text-fg">{t('Actions')}</h2>
					</div>
					<div class="mt-3 flex flex-col gap-2">
						{#each row.actions as action (action.name)}
							<Button
								variant={action.destructive ? 'danger-ghost' : 'outline'}
								class="justify-start"
								onclick={() => ask(action)}
							>
								{t(action.label)}
							</Button>
						{/each}
					</div>
				</Card>
			{/if}

			{#if related.length > 0}
				<Card padding="md" class="shadow-card">
					<div class="flex items-center gap-2">
						<span
							class="flex size-8 items-center justify-center rounded-control bg-surface-muted text-fg-secondary"
						>
							<Icon name="layers" class="size-4" />
						</span>
						<h2 class="text-sm font-semibold text-fg">{t('Related')}</h2>
					</div>
					<ul class="mt-3 flex flex-col">
						<!-- relatedHref() resolves the path; only the query is appended. -->
						<!-- eslint-disable svelte/no-navigation-without-resolve -->
						{#each related as link (`${link.table}.${link.column}`)}
							<li>
								<a
									href={relatedHref(link.table, link.column)}
									class="-mx-2 flex items-center justify-between gap-2 rounded-control px-2 py-1.5 text-sm text-fg-secondary focus-ring hover:bg-surface-muted hover:text-fg"
								>
									<span class="truncate">{humanize(link.table)}</span>
									<span class="font-mono text-xs text-fg-subtle" dir="ltr">{link.column}</span>
								</a>
							</li>
						{/each}
						<!-- eslint-enable svelte/no-navigation-without-resolve -->
					</ul>
				</Card>
			{/if}
		</div>
	</div>
{/if}

<Modal
	open={pending !== null}
	title={pending ? t(pending.label) : null}
	description={t(
		'This runs as NOVA support, through the same rules the business would follow, and is recorded in the audit log.'
	)}
	onclose={() => (pending = null)}
>
	<form id="admin-action" class="flex flex-col gap-4" onsubmit={confirm}>
		{#if actionError}
			<Alert tone="error">{actionError}</Alert>
		{/if}
		{#if pending?.requires_reason}
			<Textarea label={t('Reason')} required maxlength="500" bind:value={reason} />
		{:else}
			<Textarea label={t('Reason (optional)')} maxlength="500" bind:value={reason} />
		{/if}
	</form>
	{#snippet footer()}
		<Button variant="ghost" onclick={() => (pending = null)}>{t('Cancel')}</Button>
		<Button
			type="submit"
			form="admin-action"
			variant={pending?.destructive ? 'danger' : 'primary'}
			loading={running}
		>
			{pending ? t(pending.label) : ''}
		</Button>
	{/snippet}
</Modal>
