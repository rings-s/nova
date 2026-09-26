<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * The platform's service categories, which every salon files its services
	 * under and the marketplace filters by. Only a NOVA administrator
	 * (`users.is_superuser`, granted with `make superuser`) may open this page;
	 * the API refuses anyone else whatever this page shows.
	 *
	 * Categories are never deleted, only retired: services keep pointing at one.
	 */
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { me } from '$lib/api/auth.js';
	import { createCategory, listAllCategories, updateCategory } from '$lib/api/admin.js';
	import { formatApiError } from '$lib/utils/errors.js';

	import Container from '$lib/components/marketing/Container.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';

	/** @type {'loading'|'denied'|'ready'} */
	let status = $state('loading');
	let categories = $state(/** @type {import('$lib/api/admin.js').AdminCategory[]} */ ([]));

	let nameEn = $state('');
	let nameAr = $state('');
	let saving = $state(false);
	let error = $state(/** @type {string|null} */ (null));

	/** The row being renamed, and its draft names. */
	let editingId = $state(/** @type {string|null} */ (null));
	let draft = $state({ nameEn: '', nameAr: '' });
	let busyId = $state(/** @type {string|null} */ (null));

	$effect(() => {
		if (!authStore.isAuthenticated) {
			// eslint-disable-next-line svelte/no-navigation-without-resolve
			goto(`${resolve('/login')}?next=${encodeURIComponent('/admin/categories')}`, {
				replaceState: true
			});
			return;
		}
		let cancelled = false;
		me()
			.then(async (account) => {
				if (cancelled) return;
				if (!account.is_superuser) {
					status = 'denied';
					return;
				}
				categories = await listAllCategories();
				if (!cancelled) status = 'ready';
			})
			.catch((err) => {
				if (cancelled) return;
				status = 'denied';
				toastStore.fromError(err);
			});
		return () => {
			cancelled = true;
		};
	});

	/** @param {import('$lib/api/admin.js').AdminCategory} updated */
	function replace(updated) {
		categories = categories.map((c) => (c.id === updated.id ? updated : c));
	}

	/** @param {SubmitEvent} event */
	async function add(event) {
		event.preventDefault();
		error = null;
		saving = true;
		try {
			const created = await createCategory({ nameEn, nameAr });
			categories = [...categories, created].sort((a, b) => a.name_en.localeCompare(b.name_en));
			nameEn = '';
			nameAr = '';
			toastStore.success(t('Category added.'));
		} catch (err) {
			error = formatApiError(err);
		} finally {
			saving = false;
		}
	}

	/** @param {import('$lib/api/admin.js').AdminCategory} category */
	function startEdit(category) {
		editingId = category.id;
		draft = { nameEn: category.name_en, nameAr: category.name_ar };
	}

	/** @param {SubmitEvent} event @param {string} id */
	async function saveEdit(event, id) {
		event.preventDefault();
		busyId = id;
		try {
			replace(await updateCategory(id, { nameEn: draft.nameEn, nameAr: draft.nameAr }));
			editingId = null;
			toastStore.success(t('Category saved.'));
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			busyId = null;
		}
	}

	/** @param {import('$lib/api/admin.js').AdminCategory} category */
	async function toggleActive(category) {
		busyId = category.id;
		try {
			replace(await updateCategory(category.id, { isActive: !category.is_active }));
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			busyId = null;
		}
	}
</script>

<svelte:head><title>{t('Service categories')} — NOVA</title></svelte:head>

<Container size="md" class="py-12 sm:py-16">
	<div class="mx-auto max-w-2xl">
		<p class="text-xs font-semibold tracking-wider text-accent uppercase">
			{t('NOVA administration')}
		</p>
		<h1 class="mt-2 text-display-md font-semibold tracking-tight text-fg">
			{t('Service categories')}
		</h1>
		<p class="mt-2 text-fg-muted">
			{t(
				'Every business files its services under these, and customers filter the marketplace by them. Businesses cannot add their own.'
			)}
		</p>

		{#if status === 'loading'}
			<div class="mt-10 flex justify-center"><Spinner /></div>
		{:else if status === 'denied'}
			<EmptyState
				class="mt-10"
				title={t('Only NOVA administrators can manage categories')}
				description={t('Businesses choose from the list when they add a service.')}
			>
				{#snippet icon()}<Icon name="shield-check" class="size-6" />{/snippet}
			</EmptyState>
		{:else}
			<Card padding="lg" class="mt-8">
				<form class="flex flex-col gap-4" onsubmit={add}>
					{#if error}
						<Alert tone="error">{error}</Alert>
					{/if}
					<div class="grid gap-4 sm:grid-cols-2">
						<Input label={t('Name (English)')} required maxlength="120" bind:value={nameEn} />
						<Input
							label={t('Name (Arabic)')}
							required
							dir="rtl"
							maxlength="120"
							bind:value={nameAr}
						/>
					</div>
					<Button type="submit" loading={saving}>
						<Icon name="plus" class="size-4" />
						{t('Add category')}
					</Button>
				</form>
			</Card>

			{#if categories.length === 0}
				<EmptyState class="mt-8" title={t('No categories yet')} />
			{:else}
				<ul class="mt-8 flex flex-col gap-3">
					{#each categories as category (category.id)}
						<li>
							<Card padding="md">
								{#if editingId === category.id}
									<form
										class="flex flex-col gap-3"
										onsubmit={(event) => saveEdit(event, category.id)}
									>
										<div class="grid gap-3 sm:grid-cols-2">
											<Input
												label={t('Name (English)')}
												required
												maxlength="120"
												bind:value={draft.nameEn}
											/>
											<Input
												label={t('Name (Arabic)')}
												required
												dir="rtl"
												maxlength="120"
												bind:value={draft.nameAr}
											/>
										</div>
										<div class="flex gap-2">
											<Button type="submit" size="sm" loading={busyId === category.id}>
												{t('Save')}
											</Button>
											<Button
												type="button"
												size="sm"
												variant="ghost"
												onclick={() => (editingId = null)}
											>
												{t('Cancel')}
											</Button>
										</div>
									</form>
								{:else}
									<div class="flex flex-wrap items-center justify-between gap-3">
										<div class="min-w-0">
											<p class="font-semibold text-fg">
												{category.name_en}
												<span class="text-fg-muted" dir="rtl">· {category.name_ar}</span>
											</p>
											<p class="mt-0.5 text-xs text-fg-subtle" dir="ltr">{category.slug}</p>
										</div>
										<div class="flex items-center gap-2">
											{#if !category.is_active}
												<Badge tone="warning">{t('Retired')}</Badge>
											{/if}
											<Button size="sm" variant="ghost" onclick={() => startEdit(category)}>
												{t('Rename')}
											</Button>
											<Button
												size="sm"
												variant={category.is_active ? 'danger-ghost' : 'outline'}
												loading={busyId === category.id}
												onclick={() => toggleActive(category)}
											>
												{category.is_active ? t('Retire') : t('Restore')}
											</Button>
										</div>
									</div>
								{/if}
							</Card>
						</li>
					{/each}
				</ul>
			{/if}
		{/if}
	</div>
</Container>
