<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * The platform console's shell, for NOVA administrators (`users.is_superuser`,
	 * granted with `make superuser`). A sidebar of every table, grouped by the
	 * module that owns it; the pages below browse them.
	 *
	 * The API refuses anyone else whatever this shows, and records every read.
	 */
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { GROUPS, consoleState, humanize, loadConsole } from '$lib/admin/console.svelte.js';

	import Spinner from '$lib/components/ui/Spinner.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import { fieldBase, fieldBorder } from '$lib/components/ui/styles.js';

	let { children } = $props();

	let tableFilter = $state('');

	$effect(() => {
		if (!authStore.isAuthenticated) {
			// eslint-disable-next-line svelte/no-navigation-without-resolve
			goto(`${resolve('/login')}?next=${encodeURIComponent(page.url.pathname)}`, {
				replaceState: true
			});
			return;
		}
		loadConsole().catch((err) => toastStore.fromError(err));
	});

	let groups = $derived(
		GROUPS.map(([key, label]) => ({
			key,
			label,
			tables: consoleState.tables.filter(
				(table) => table.group === key && table.name.includes(tableFilter.trim().toLowerCase())
			)
		})).filter((group) => group.tables.length > 0)
	);

	let currentTable = $derived(page.params.table ?? '');

	let jumpOptions = $derived(
		consoleState.tables.map((table) => ({ value: table.name, label: humanize(table.name) }))
	);

	/** @param {string} path */
	function isActive(path) {
		return page.url.pathname === path;
	}
</script>

<svelte:head><title>{t('NOVA administration')} — NOVA</title></svelte:head>

{#if consoleState.status === 'loading'}
	<div class="flex justify-center py-24"><Spinner /></div>
{:else if consoleState.status === 'denied'}
	<EmptyState
		class="mx-auto my-24 max-w-md px-4"
		title={t('Only NOVA administrators can open this page')}
		description={t('Ask a NOVA administrator if you need access.')}
	>
		{#snippet icon()}<Icon name="shield-check" class="size-6" />{/snippet}
	</EmptyState>
{:else}
	<div class="mx-auto flex w-full max-w-[1600px] gap-5 px-4 py-5 sm:px-6 lg:gap-7 lg:px-8 lg:py-8">
		<aside class="hidden w-64 shrink-0 lg:block" aria-label={t('Tables')}>
			<div
				class="sticky top-6 flex max-h-[calc(100dvh-3rem)] flex-col overflow-hidden rounded-panel border border-line bg-surface shadow-card"
			>
				<div class="border-b border-line px-4 py-4">
					<p class="text-xs font-semibold tracking-wider text-accent uppercase">
						{t('NOVA administration')}
					</p>
					<p class="mt-1 text-xs text-fg-subtle">{t('Platform')}</p>
					<nav class="mt-4 flex flex-col gap-1">
						<a
							href={resolve('/admin')}
							class={[
								'flex items-center gap-2 rounded-control px-3 py-2 text-sm font-medium focus-ring transition-colors',
								isActive(resolve('/admin'))
									? 'bg-accent-soft text-accent'
									: 'text-fg-secondary hover:bg-surface-muted hover:text-fg'
							].join(' ')}
						>
							<Icon name="home" class="size-4" />
							{t('Overview')}
						</a>
						<a
							href={resolve('/admin/categories')}
							class={[
								'flex items-center gap-2 rounded-control px-3 py-2 text-sm font-medium focus-ring transition-colors',
								isActive(resolve('/admin/categories'))
									? 'bg-accent-soft text-accent'
									: 'text-fg-secondary hover:bg-surface-muted hover:text-fg'
							].join(' ')}
						>
							<Icon name="layers" class="size-4" />
							{t('Service categories')}
						</a>
					</nav>
				</div>

				<div class="px-3 pt-4">
					<label class="relative block">
						<span class="sr-only">{t('Filter tables')}</span>
						<Icon
							name="search"
							class="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-fg-subtle"
						/>
						<input
							type="search"
							class={`${fieldBase} ${fieldBorder} h-10 rounded-control ps-9 text-sm`}
							placeholder={t('Filter tables')}
							bind:value={tableFilter}
						/>
					</label>
				</div>

				<nav class="min-h-0 flex-1 overflow-y-auto px-3 pb-4">
					{#each groups as group (group.key)}
						<p
							class="mt-5 mb-1 px-2 text-[10px] font-semibold tracking-[0.12em] text-fg-subtle uppercase first:mt-1"
						>
							{t(group.label)}
						</p>
						<ul class="flex flex-col gap-0.5">
							{#each group.tables as table (table.name)}
								<li>
									<a
										href={resolve('/admin/tables/[table]', { table: table.name })}
										aria-current={currentTable === table.name ? 'page' : undefined}
										class={[
											'flex items-center justify-between gap-2 rounded-control px-2 py-1.5 text-[13px] focus-ring transition-colors',
											currentTable === table.name
												? 'bg-surface-muted font-semibold text-fg'
												: 'text-fg-secondary hover:bg-surface-muted hover:text-fg'
										].join(' ')}
									>
										<span class="truncate">{humanize(table.name)}</span>
										<span
											class="rounded-full bg-canvas px-1.5 py-0.5 text-[10px] text-fg-subtle tabular-nums"
											>{table.estimated_rows}</span
										>
									</a>
								</li>
							{/each}
						</ul>
					{/each}
				</nav>
			</div>
		</aside>

		<div class="min-w-0 flex-1">
			<div
				class="mb-4 flex flex-wrap items-end gap-3 rounded-card border border-line bg-surface p-3 shadow-card lg:hidden"
			>
				<a href={resolve('/admin')} class="text-sm font-medium text-accent hover:underline">
					{t('Overview')}
				</a>
				<div class="min-w-48 flex-1">
					<Select
						label={t('Table')}
						options={jumpOptions}
						placeholder={t('Choose a table')}
						value={currentTable}
						onchange={(/** @type {Event} */ event) => {
							const table = /** @type {HTMLSelectElement} */ (event.currentTarget).value;
							if (table) goto(resolve('/admin/tables/[table]', { table }));
						}}
					/>
				</div>
			</div>
			{@render children()}
		</div>
	</div>
{/if}
