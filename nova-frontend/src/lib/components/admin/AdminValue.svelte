<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * One stored value in the platform console. A foreign key links to the row it
	 * names; a masked column says so rather than looking empty; `full` shows
	 * long text and JSON whole (the row page) instead of clipped (the list).
	 */
	import { resolve } from '$app/paths';
	import { formatDateTime } from '$lib/utils/datetime.js';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';

	/**
	 * @type {{
	 *   value: unknown,
	 *   column: import('$lib/api/admin.js').AdminColumn,
	 *   full?: boolean
	 * }}
	 */
	let { value, column, full = false } = $props();

	let json = $derived(
		column.type === 'json' && value !== null ? JSON.stringify(value, null, full ? 2 : 0) : ''
	);
</script>

{#if value === null || value === undefined}
	<span class="text-fg-subtle">—</span>
{:else if column.masked}
	<span class="inline-flex items-center gap-1 text-fg-muted" dir="ltr" title={t('Hidden')}>
		<Icon name="lock" class="size-3.5" />
		<span class="font-mono text-xs">{String(value)}</span>
	</span>
{:else if column.type === 'boolean'}
	<Badge tone={value ? 'success' : 'neutral'} size="sm">{value ? t('Yes') : t('No')}</Badge>
{:else if column.type === 'datetime'}
	<span class="whitespace-nowrap tabular-nums" title={String(value)}>
		{formatDateTime(String(value))}
	</span>
{:else if column.type === 'enum'}
	<Badge size="sm">{String(value)}</Badge>
{:else if column.references}
	<a
		href={resolve('/admin/tables/[table]/[id]', { table: column.references, id: String(value) })}
		class="rounded-control font-mono text-xs text-accent focus-ring hover:underline"
		dir="ltr"
		title={String(value)}
	>
		{full ? String(value) : `${String(value).slice(0, 8)}…`}
	</a>
{:else if column.type === 'uuid'}
	<span class="font-mono text-xs" dir="ltr" title={String(value)}>
		{full ? String(value) : `${String(value).slice(0, 8)}…`}
	</span>
{:else if column.type === 'json'}
	{#if full}
		<pre
			class="max-h-96 overflow-auto rounded-control bg-surface-muted p-3 font-mono text-xs"
			dir="ltr">{json}</pre>
	{:else}
		<span class="block max-w-64 truncate font-mono text-xs text-fg-muted" dir="ltr">{json}</span>
	{/if}
{:else if full}
	<span class="break-words whitespace-pre-wrap">{String(value)}</span>
{:else}
	<span class="block max-w-64 truncate" title={String(value)}>{String(value)}</span>
{/if}
