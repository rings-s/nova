<script>
	import { joinQueue } from '../../api/queue.js';
	import { pickBilingual } from '../../utils/bilingual.js';
	import Select from '../ui/Select.svelte';
	import Input from '../ui/Input.svelte';
	import Button from '../ui/Button.svelte';
	import Alert from '../ui/Alert.svelte';

	/**
	 * @type {{
	 *   tenantId: string,
	 *   queueId: string,
	 *   services: import('../../api/catalog.js').Service[],
	 *   providers?: import('../../api/catalog.js').Provider[],
	 *   locale?: 'en'|'ar',
	 *   onjoined?: (entry: import('../../api/queue.js').QueueEntry) => void
	 * }}
	 */
	let { tenantId, queueId, services, providers = [], locale = 'en', onjoined } = $props();

	let serviceId = $state('');
	let providerId = $state('');
	let partySize = $state(1);
	let error = $state(/** @type {string|null} */ (null));
	let loading = $state(false);

	async function handleSubmit(event) {
		event.preventDefault();
		error = null;
		loading = true;
		try {
			const entry = await joinQueue(tenantId, queueId, {
				serviceId,
				providerId: providerId || null,
				partySize
			});
			onjoined?.(entry);
		} catch (err) {
			error = err?.message ?? 'Could not join the queue.';
		} finally {
			loading = false;
		}
	}
</script>

<form class="flex flex-col gap-4" onsubmit={handleSubmit}>
	{#if error}
		<Alert tone="error">{error}</Alert>
	{/if}
	<Select
		label="Service"
		required
		bind:value={serviceId}
		options={services.map((service) => ({
			value: service.id,
			label: pickBilingual(service, 'name', locale)
		}))}
	/>
	{#if providers.length > 0}
		<Select
			label="Preferred provider"
			hint="Optional — leave unset for the next available."
			bind:value={providerId}
			options={providers.map((provider) => ({
				value: provider.id,
				label: pickBilingual(provider, 'name', locale)
			}))}
		/>
	{/if}
	<Input type="number" label="Party size" min="1" max="20" bind:value={partySize} />
	<Button type="submit" {loading} fullWidth disabled={!serviceId}>Join the queue</Button>
</form>
