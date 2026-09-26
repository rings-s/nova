<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * The business's cover and gallery, as the dashboard manages them. Uploads
	 * go to the API as the raw file; the server re-encodes every image, so the
	 * checks here (type, size) only save a round trip on an obvious mistake.
	 */
	import { apiAssetUrl } from '../../api/client.js';
	import {
		deleteBusinessPhoto,
		listBusinessPhotos,
		updateBusinessPhoto,
		uploadBusinessPhoto
	} from '../../api/catalog.js';
	import { toastStore } from '../../stores/toast.svelte.js';
	import Button from '../ui/Button.svelte';
	import Icon from '../ui/Icon.svelte';
	import Skeleton from '../ui/Skeleton.svelte';
	import Spinner from '../ui/Spinner.svelte';

	/** @type {{ tenantId: string, businessId: string, canEdit?: boolean }} */
	let { tenantId, businessId, canEdit = false } = $props();

	const MAX_GALLERY = 12;
	const MAX_BYTES = 10 * 1024 * 1024;
	const ACCEPT = 'image/jpeg,image/png,image/webp';

	let loading = $state(true);
	let photos = $state(/** @type {import('../../api/catalog.js').BusinessPhoto[]} */ ([]));
	/** Uploads in flight, per kind, shown as placeholders. */
	let pending = $state({ cover: 0, gallery: 0 });
	let removing = $state(/** @type {string|null} */ (null));
	let dragOver = $state(/** @type {'cover'|'gallery'|null} */ (null));

	let cover = $derived(photos.find((photo) => photo.kind === 'cover') ?? null);
	let gallery = $derived(photos.filter((photo) => photo.kind === 'gallery'));
	let galleryRoom = $derived(MAX_GALLERY - gallery.length - pending.gallery);

	/** @type {HTMLInputElement|undefined} */ let coverInput = $state();
	/** @type {HTMLInputElement|undefined} */ let galleryInput = $state();

	$effect(() => {
		const tenant = tenantId;
		const business = businessId;
		let cancelled = false;
		loading = true;
		listBusinessPhotos(tenant, business)
			.then((result) => {
				if (!cancelled) photos = result;
			})
			.catch((err) => toastStore.fromError(err))
			.finally(() => {
				if (!cancelled) loading = false;
			});
		return () => {
			cancelled = true;
		};
	});

	/** @param {File} file */
	function problemWith(file) {
		if (!ACCEPT.split(',').includes(file.type))
			return t('{file}: use a JPEG, PNG or WebP image.', { file: file.name });
		if (file.size > MAX_BYTES) return t('{file} is over 10 MB.', { file: file.name });
		return null;
	}

	/** @param {FileList|File[]|null|undefined} list @param {'cover'|'gallery'} kind */
	async function upload(list, kind) {
		if (!canEdit || !list) return;
		let files = [...list];
		if (kind === 'cover') files = files.slice(0, 1);
		if (kind === 'gallery' && files.length > galleryRoom) {
			toastStore.info(
				t('The gallery holds {max} photos; adding the first {count}.', {
					max: MAX_GALLERY,
					count: Math.max(0, galleryRoom)
				})
			);
			files = files.slice(0, Math.max(0, galleryRoom));
		}
		for (const file of files) {
			const problem = problemWith(file);
			if (problem) {
				toastStore.error(problem);
				continue;
			}
			pending[kind] += 1;
			try {
				const photo = await uploadBusinessPhoto(tenantId, businessId, file, kind);
				// A new cover replaces the old one on the server; mirror that.
				photos =
					kind === 'cover'
						? [photo, ...photos.filter((p) => p.kind !== 'cover')]
						: [...photos, photo];
			} catch (err) {
				toastStore.fromError(err);
			} finally {
				pending[kind] -= 1;
			}
		}
		if (files.length)
			toastStore.success(kind === 'cover' ? t('Cover photo updated.') : t('Photos added.'));
	}

	/** @param {import('../../api/catalog.js').BusinessPhoto} photo */
	async function remove(photo) {
		removing = photo.id;
		try {
			await deleteBusinessPhoto(tenantId, photo.id);
			photos = photos.filter((p) => p.id !== photo.id);
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			removing = null;
		}
	}

	/** A photo being made the cover or moved, so its buttons show progress. */
	let arranging = $state(/** @type {string|null} */ (null));

	/**
	 * Runs one rearrangement, then reads the photos back: the server decides
	 * where a demoted cover lands, so the page shows its answer, not a guess.
	 * @param {string} photoId @param {() => Promise<unknown>} change
	 */
	async function rearrange(photoId, change) {
		arranging = photoId;
		try {
			await change();
			photos = await listBusinessPhotos(tenantId, businessId);
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			arranging = null;
		}
	}

	/** @param {import('../../api/catalog.js').BusinessPhoto} photo */
	function makeCover(photo) {
		return rearrange(photo.id, () => updateBusinessPhoto(tenantId, photo.id, { kind: 'cover' }));
	}

	/**
	 * Swaps a gallery photo with its neighbour, earlier (-1) or later (+1).
	 * @param {number} index @param {-1|1} step
	 */
	function move(index, step) {
		const photo = gallery[index];
		const other = gallery[index + step];
		if (!photo || !other) return;
		return rearrange(photo.id, async () => {
			await updateBusinessPhoto(tenantId, photo.id, { position: index + step });
			await updateBusinessPhoto(tenantId, other.id, { position: index });
		});
	}

	/** @param {DragEvent} event @param {'cover'|'gallery'} kind */
	function drop(event, kind) {
		event.preventDefault();
		dragOver = null;
		upload(event.dataTransfer?.files, kind);
	}

	/** @param {DragEvent} event @param {'cover'|'gallery'} kind */
	function dragEnter(event, kind) {
		if (!canEdit) return;
		event.preventDefault();
		dragOver = kind;
	}
</script>

<div class="flex flex-col gap-8">
	<!-- Cover -->
	<section aria-labelledby="cover-heading">
		<div class="mb-3 flex flex-wrap items-end justify-between gap-2">
			<div>
				<h2 id="cover-heading" class="text-base font-semibold tracking-tight text-fg">
					{t('Cover photo')}
				</h2>
				<p class="text-sm text-fg-muted">
					{t('The first thing customers see, on search results and at the top of your page.')}
				</p>
			</div>
			{#if canEdit && cover}
				<div class="flex gap-2">
					<Button size="sm" variant="outline" onclick={() => coverInput?.click()}
						>{t('Replace')}</Button
					>
					<Button
						size="sm"
						variant="danger-ghost"
						loading={removing === cover.id}
						onclick={() => cover && remove(cover)}
					>
						{t('Remove')}
					</Button>
				</div>
			{/if}
		</div>

		{#if loading}
			<Skeleton class="aspect-[16/7] w-full rounded-card" />
		{:else if pending.cover}
			<div
				class="flex aspect-[16/7] w-full items-center justify-center rounded-card border border-line bg-surface-sunken"
			>
				<Spinner label={t('Uploading cover')} />
			</div>
		{:else if cover}
			<img
				src={apiAssetUrl(cover.urls.large)}
				alt={t('Cover')}
				class="aspect-[16/7] w-full rounded-card border border-line object-cover shadow-card"
			/>
		{:else if canEdit}
			<button
				type="button"
				onclick={() => coverInput?.click()}
				ondragenter={(e) => dragEnter(e, 'cover')}
				ondragover={(e) => dragEnter(e, 'cover')}
				ondragleave={() => (dragOver = null)}
				ondrop={(e) => drop(e, 'cover')}
				class={[
					'flex aspect-[16/7] w-full flex-col items-center justify-center gap-2 rounded-card border-2 border-dashed text-sm focus-ring transition-colors',
					dragOver === 'cover'
						? 'border-brand-500 bg-accent-soft text-accent'
						: 'border-line-strong bg-surface-sunken text-fg-muted hover:border-fg-subtle hover:text-fg'
				].join(' ')}
			>
				<Icon name="plus" class="size-6" />
				<span class="font-medium">{t('Add a cover photo')}</span>
				<span class="text-xs">{t('Click or drop an image · JPEG, PNG or WebP, up to 10 MB')}</span>
			</button>
		{:else}
			<p class="rounded-card border border-line bg-surface-sunken p-6 text-sm text-fg-muted">
				{t('No cover photo yet.')}
			</p>
		{/if}
		<input
			bind:this={coverInput}
			type="file"
			accept={ACCEPT}
			class="sr-only"
			tabindex="-1"
			aria-hidden="true"
			onchange={(e) => {
				upload(e.currentTarget.files, 'cover');
				e.currentTarget.value = '';
			}}
		/>
	</section>

	<!-- Gallery -->
	<section aria-labelledby="gallery-heading">
		<div class="mb-3">
			<h2 id="gallery-heading" class="text-base font-semibold tracking-tight text-fg">
				{t('Gallery')}
				<span class="ms-1 text-sm font-normal text-fg-muted tabular-nums"
					>{gallery.length}/{MAX_GALLERY}</span
				>
			</h2>
			<p class="text-sm text-fg-muted">{t('Your space, your work and your team, on your page.')}</p>
		</div>

		{#if loading}
			<div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
				{#each [0, 1, 2, 3] as n (n)}<Skeleton class="aspect-square rounded-card" />{/each}
			</div>
		{:else}
			<ul class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
				{#each gallery as photo, index (photo.id)}
					<li class="group relative">
						<img
							src={apiAssetUrl(photo.urls.thumb)}
							alt=""
							loading="lazy"
							class="aspect-square w-full rounded-card border border-line object-cover"
						/>
						{#if canEdit}
							<div
								class="absolute inset-x-2 bottom-2 flex items-center justify-between gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100"
							>
								<div class="flex gap-1">
									<button
										type="button"
										onclick={() => move(index, -1)}
										disabled={index === 0 || arranging !== null}
										aria-label={t('Move earlier')}
										class="flex size-8 items-center justify-center rounded-full bg-slate-950/70 text-white focus-ring backdrop-blur disabled:opacity-40"
									>
										<Icon name="chevron-left" class="size-4 rtl:rotate-180" />
									</button>
									<button
										type="button"
										onclick={() => move(index, 1)}
										disabled={index === gallery.length - 1 || arranging !== null}
										aria-label={t('Move later')}
										class="flex size-8 items-center justify-center rounded-full bg-slate-950/70 text-white focus-ring backdrop-blur disabled:opacity-40"
									>
										<Icon name="chevron-right" class="size-4 rtl:rotate-180" />
									</button>
								</div>
								<button
									type="button"
									onclick={() => makeCover(photo)}
									disabled={arranging !== null}
									class="flex h-8 items-center gap-1 rounded-full bg-slate-950/70 px-3 text-xs font-medium text-white focus-ring backdrop-blur disabled:opacity-40"
								>
									{#if arranging === photo.id}<Spinner size="sm" class="text-white" />{:else}<Icon
											name="star"
											class="size-3.5"
										/>{/if}
									{t('Make cover')}
								</button>
							</div>
							<button
								type="button"
								onclick={() => remove(photo)}
								disabled={removing === photo.id}
								aria-label={t('Remove photo')}
								class="absolute end-2 top-2 flex size-8 items-center justify-center rounded-full bg-slate-950/70 text-white opacity-0 focus-ring backdrop-blur transition-opacity group-hover:opacity-100 focus-visible:opacity-100 disabled:opacity-100"
							>
								{#if removing === photo.id}<Spinner size="sm" class="text-white" />{:else}<Icon
										name="x"
										class="size-4"
									/>{/if}
							</button>
						{/if}
					</li>
				{/each}
				{#each Array.from({ length: pending.gallery }, (_, i) => i) as n (n)}
					<li
						class="flex aspect-square items-center justify-center rounded-card border border-line bg-surface-sunken"
					>
						<Spinner size="sm" label={t('Uploading')} />
					</li>
				{/each}
				{#if canEdit && galleryRoom > 0}
					<li>
						<button
							type="button"
							onclick={() => galleryInput?.click()}
							ondragenter={(e) => dragEnter(e, 'gallery')}
							ondragover={(e) => dragEnter(e, 'gallery')}
							ondragleave={() => (dragOver = null)}
							ondrop={(e) => drop(e, 'gallery')}
							class={[
								'flex aspect-square w-full flex-col items-center justify-center gap-1.5 rounded-card border-2 border-dashed text-sm focus-ring transition-colors',
								dragOver === 'gallery'
									? 'border-brand-500 bg-accent-soft text-accent'
									: 'border-line-strong bg-surface-sunken text-fg-muted hover:border-fg-subtle hover:text-fg'
							].join(' ')}
						>
							<Icon name="plus" class="size-5" />
							<span class="font-medium">{t('Add photos')}</span>
						</button>
					</li>
				{/if}
			</ul>
			{#if !canEdit && gallery.length === 0}
				<p class="rounded-card border border-line bg-surface-sunken p-6 text-sm text-fg-muted">
					{t('No gallery photos yet.')}
				</p>
			{/if}
		{/if}
		<input
			bind:this={galleryInput}
			type="file"
			accept={ACCEPT}
			multiple
			class="sr-only"
			tabindex="-1"
			aria-hidden="true"
			onchange={(e) => {
				upload(e.currentTarget.files, 'gallery');
				e.currentTarget.value = '';
			}}
		/>
	</section>
</div>
