<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * The console's front page: every table, grouped by module, with Postgres's
	 * estimated row counts. The layout has already checked the account.
	 */
	import { resolve } from '$app/paths';
	import { GROUPS, consoleState, humanize } from '$lib/admin/console.svelte.js';

	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';

	let groups = $derived(
		GROUPS.map(([key, label]) => ({
			key,
			label,
			tables: consoleState.tables.filter((table) => table.group === key)
		})).filter((group) => group.tables.length > 0)
	);
	let estimatedRows = $derived(
		consoleState.tables.reduce((total, table) => total + table.estimated_rows, 0)
	);
</script>

<PageHeader
	eyebrow={t('NOVA administration')}
	title={t('Every table')}
	subtitle={t(
		'Browse any table across every business. Secrets are hidden, and nothing here edits a row directly: changes go through each table’s actions.'
	)}
>
	{#snippet actions()}
		<Button variant="outline" href={resolve('/admin/tables/[table]', { table: 'admin_audit_log' })}>
			<Icon name="receipt" class="size-4" />
			{t('Open the audit log')}
		</Button>
	{/snippet}
</PageHeader>

<section class="mb-7 grid gap-3 sm:grid-cols-2" aria-label={t('Platform')}>
	<div
		class="flex items-center gap-4 rounded-card border border-line bg-surface p-4 shadow-card sm:p-5"
	>
		<span
			class="flex size-11 shrink-0 items-center justify-center rounded-control bg-accent-soft text-accent"
		>
			<Icon name="table" class="size-5" />
		</span>
		<div>
			<p class="text-xs font-medium text-fg-muted">{t('Every table')}</p>
			<p class="mt-0.5 text-2xl font-semibold tracking-tight text-fg tabular-nums">
				{consoleState.tables.length}
			</p>
		</div>
	</div>
	<div
		class="flex items-center gap-4 rounded-card border border-line bg-surface p-4 shadow-card sm:p-5"
	>
		<span
			class="flex size-11 shrink-0 items-center justify-center rounded-control bg-surface-muted text-fg-secondary"
		>
			<Icon name="chart-bar" class="size-5" />
		</span>
		<div>
			<p class="text-xs font-medium text-fg-muted">{t('Estimated rows')}</p>
			<p class="mt-0.5 text-2xl font-semibold tracking-tight text-fg tabular-nums">
				{estimatedRows.toLocaleString()}
			</p>
		</div>
	</div>
</section>

<div class="mb-3 flex items-center justify-between gap-3">
	<h2 class="text-sm font-semibold text-fg">{t('Browse by module')}</h2>
	<span class="text-xs text-fg-muted">{groups.length}</span>
</div>

<div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
	{#each groups as group (group.key)}
		<Card padding="none" class="overflow-hidden">
			<div class="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
				<div class="flex min-w-0 items-center gap-2.5">
					<span
						class="flex size-8 shrink-0 items-center justify-center rounded-control bg-accent-soft text-accent"
					>
						<Icon name="layers" class="size-4" />
					</span>
					<h2 class="truncate text-sm font-semibold text-fg">{t(group.label)}</h2>
				</div>
				<span class="rounded-full bg-surface-muted px-2 py-0.5 text-xs text-fg-muted tabular-nums">
					{group.tables.length}
				</span>
			</div>
			<ul class="divide-y divide-line-subtle px-2 py-1">
				{#each group.tables as table (table.name)}
					<li>
						<a
							href={resolve('/admin/tables/[table]', { table: table.name })}
							class="group flex items-center justify-between gap-3 rounded-control px-2.5 py-2.5 text-sm text-fg-secondary focus-ring transition-colors hover:bg-surface-muted hover:text-fg"
						>
							<span class="flex min-w-0 items-center gap-2">
								<Icon name="table" class="size-3.5 text-fg-subtle" />
								<span class="truncate">{humanize(table.name)}</span>
							</span>
							<span class="flex shrink-0 items-center gap-2">
								<span class="text-xs text-fg-subtle tabular-nums" title={t('Estimated rows')}>
									{table.estimated_rows.toLocaleString()}
								</span>
								<Icon
									name="chevron-right"
									class="size-3.5 text-fg-subtle transition-transform group-hover:translate-x-0.5 rtl:rotate-180"
								/>
							</span>
						</a>
					</li>
				{/each}
			</ul>
		</Card>
	{/each}
</div>
