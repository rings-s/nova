<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * Adds a row to a table, as given (the API's `create_row`). Columns left
	 * blank take their defaults; the new row opens on success.
	 */
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { createRow, describeTable } from '$lib/api/admin.js';
	import { humanize } from '$lib/admin/console.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { formatApiError } from '$lib/utils/errors.js';

	import AdminRowForm from '$lib/components/admin/AdminRowForm.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';

	let table = $derived(page.params.table ?? '');

	let detail = $state(/** @type {import('$lib/api/admin.js').AdminTableDetail|null} */ (null));
	let error = $state(/** @type {string|null} */ (null));
	let saving = $state(false);
	let saveError = $state(/** @type {string|null} */ (null));

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

	/** @param {Record<string, unknown>} values */
	async function create(values) {
		saving = true;
		saveError = null;
		try {
			const row = await createRow(table, values);
			toastStore.success(t('Row added.'));
			await goto(resolve('/admin/tables/[table]/[id]', { table, id: row.id }));
		} catch (err) {
			saveError = formatApiError(err);
		} finally {
			saving = false;
		}
	}
</script>

<svelte:head
	><title>{t('Add row')} · {humanize(table)} — {t('NOVA administration')}</title></svelte:head
>

<a
	href={resolve('/admin/tables/[table]', { table })}
	class="mb-4 inline-flex items-center gap-1.5 rounded-control text-sm font-medium text-accent focus-ring hover:underline"
>
	<Icon name="chevron-left" class="size-4 rtl:rotate-180" />
	{humanize(table)}
</a>
<PageHeader eyebrow={t('NOVA administration')} title={t('Add row')} subtitle={table} />

{#if error}
	<Alert tone="error" class="mt-6">{error}</Alert>
{:else if !detail}
	<div class="mt-2 flex flex-col gap-2 rounded-card border border-line bg-surface p-5">
		{#each { length: 6 }, index (index)}
			<Skeleton class="h-10 w-full" />
		{/each}
	</div>
{:else if !detail.editable}
	<Alert tone="info" class="mt-6">{t('Rows can’t be added to this table from the console.')}</Alert>
{:else}
	<Card padding="none" class="mt-2 overflow-hidden shadow-raised">
		<div class="flex flex-col gap-5 p-5">
			<Alert tone="warning">
				{t(
					'The row is saved exactly as entered: no business rule, notification or event runs. Fields left blank take their defaults.'
				)}
			</Alert>
			{#if saveError}
				<Alert tone="error">{saveError}</Alert>
			{/if}
			<AdminRowForm id="admin-create" columns={detail.columns} onsubmit={create} />
			<div class="flex justify-end gap-2 border-t border-line-subtle pt-4">
				<Button variant="ghost" href={resolve('/admin/tables/[table]', { table })}>
					{t('Cancel')}
				</Button>
				<Button type="submit" form="admin-create" loading={saving}>{t('Add row')}</Button>
			</div>
		</div>
	</Card>
{/if}
