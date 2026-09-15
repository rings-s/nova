<script>
	/**
	 * Presentational grid over assets the caller already fetched
	 * (`listBusinessMedia`, media.js). Assets have no directly renderable URL
	 * by default — "Get link" mints a fresh share link from Nextcloud on click,
	 * matching the backend's own "generated on demand rather than stored" rule.
	 */
	import { getMediaLink } from '../../api/media.js';
	import Card from '../ui/Card.svelte';
	import Badge from '../ui/Badge.svelte';
	import Button from '../ui/Button.svelte';
	import { toastStore } from '../../stores/toast.svelte.js';

	/**
	 * @type {{
	 *   tenantId: string,
	 *   assets: import('../../api/media.js').MediaAsset[],
	 *   ondelete?: (assetId: string) => void
	 * }}
	 */
	let { tenantId, assets, ondelete } = $props();

	let linkLoadingId = $state(/** @type {string|null} */ (null));

	async function copyLink(assetId) {
		linkLoadingId = assetId;
		try {
			const { url } = await getMediaLink(tenantId, assetId);
			await navigator.clipboard?.writeText(url);
			toastStore.success('Link copied.');
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			linkLoadingId = null;
		}
	}
</script>

<div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
	{#each assets as asset (asset.id)}
		<Card padding="sm">
			<p class="truncate text-sm font-medium text-slate-900 dark:text-slate-100" title={asset.file_name}>
				{asset.file_name}
			</p>
			<div class="mt-1 flex items-center gap-1.5">
				<Badge size="sm" tone={asset.is_ready ? 'success' : 'warning'}>
					{asset.is_ready ? asset.kind : 'processing'}
				</Badge>
			</div>
			<div class="mt-2 flex gap-1.5">
				<Button
					size="sm"
					variant="ghost"
					loading={linkLoadingId === asset.id}
					disabled={!asset.is_ready}
					onclick={() => copyLink(asset.id)}
				>
					Copy link
				</Button>
				{#if ondelete}
					<Button size="sm" variant="ghost" onclick={() => ondelete(asset.id)}>Delete</Button>
				{/if}
			</div>
		</Card>
	{/each}
</div>
