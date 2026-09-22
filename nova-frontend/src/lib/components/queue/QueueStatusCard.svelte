<script>
	/**
	 * Polls a customer's own queue entry — the one read a waiting customer
	 * actually needs ("how much longer?"). Staff should use `listQueueEntries`
	 * (queue.js) directly for the full line instead.
	 */
	import { getQueueEntry } from '../../api/queue.js';
	import Card from '../ui/Card.svelte';
	import Badge from '../ui/Badge.svelte';
	import Spinner from '../ui/Spinner.svelte';
	import { errorMessage } from '../../utils/errors.js';

	/** @type {{ tenantId: string, entryId: string, pollIntervalMs?: number }} */
	let { tenantId, entryId, pollIntervalMs = 15000 } = $props();

	let entry = $state(/** @type {import('../../api/queue.js').QueueEntry|null} */ (null));
	let error = $state(/** @type {string|null} */ (null));

	/** @type {Record<string, 'neutral'|'success'|'warning'|'error'|'info'|'accent'>} */
	const statusTone = {
		waiting: 'info',
		called: 'accent',
		checked_in: 'accent',
		in_service: 'accent',
		completed: 'success',
		missed: 'warning',
		cancelled: 'neutral'
	};

	$effect(() => {
		let cancelled = false;

		async function poll() {
			try {
				const next = await getQueueEntry(tenantId, entryId);
				if (!cancelled) {
					entry = next;
					error = null;
				}
			} catch (err) {
				if (!cancelled) error = errorMessage(err);
			}
		}

		poll();
		const interval = setInterval(poll, pollIntervalMs);
		return () => {
			cancelled = true;
			clearInterval(interval);
		};
	});
</script>

<Card>
	{#if error && !entry}
		<p class="text-sm text-red-600">{error}</p>
	{:else if !entry}
		<div class="flex justify-center py-4"><Spinner size="sm" /></div>
	{:else}
		<div class="flex items-center justify-between">
			<div>
				<p class="text-sm text-fg-muted">Your place in line</p>
				<p class="text-3xl font-semibold text-fg">
					{entry.place_in_line ?? '—'}
				</p>
				{#if entry.estimated_wait_minutes !== null}
					<p class="text-sm text-fg-muted">
						~{entry.estimated_wait_minutes} min estimated wait
					</p>
				{/if}
			</div>
			<Badge tone={statusTone[entry.status] ?? 'neutral'}>{entry.status}</Badge>
		</div>
	{/if}
</Card>
