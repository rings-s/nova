<script>
	/**
	 * Requests a Nextcloud authorisation, PUTs the file straight there, then
	 * confirms — the bytes never pass through this app's own API server
	 * (nova_backend/app/modules/media, docs/02 section 4).
	 */
	import { uploadMediaAsset } from '../../api/media.js';
	import Button from '../ui/Button.svelte';
	import Alert from '../ui/Alert.svelte';

	/**
	 * @type {{
	 *   tenantId: string,
	 *   businessId: string,
	 *   kind: import('../../api/media.js').MediaAssetKind,
	 *   locationId?: string|null,
	 *   onuploaded?: (asset: import('../../api/media.js').MediaAsset) => void
	 * }}
	 */
	let { tenantId, businessId, kind, locationId = null, onuploaded } = $props();

	let uploading = $state(false);
	let error = $state(/** @type {string|null} */ (null));
	/** @type {HTMLInputElement|undefined} */
	let fileInput;

	async function handleChange() {
		const file = fileInput?.files?.[0];
		if (!file) return;
		error = null;
		uploading = true;
		try {
			const asset = await uploadMediaAsset(tenantId, { businessId, locationId, kind, file });
			onuploaded?.(asset);
		} catch (err) {
			error = err?.message ?? 'Upload failed.';
		} finally {
			uploading = false;
			if (fileInput) fileInput.value = '';
		}
	}
</script>

<div class="flex flex-col gap-2">
	{#if error}
		<Alert tone="error">{error}</Alert>
	{/if}
	<input bind:this={fileInput} type="file" accept="image/*" class="hidden" onchange={handleChange} />
	<Button loading={uploading} onclick={() => fileInput?.click()} variant="outline">
		{uploading ? 'Uploading…' : 'Upload image'}
	</Button>
</div>
