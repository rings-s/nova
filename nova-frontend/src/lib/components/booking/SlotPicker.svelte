<script>
	/**
	 * Fetches and renders bookable slots for one provider/service pair. Works
	 * against either the authenticated `getAvailability` (booking.js) or the
	 * public `getPublicAvailability` (discovery.js) — pass `source` to pick.
	 */
	import { getAvailability } from '../../api/booking.js';
	import { getPublicAvailability } from '../../api/discovery.js';
	import { formatDate, formatTime } from '../../utils/datetime.js';
	import Spinner from '../ui/Spinner.svelte';
	import Alert from '../ui/Alert.svelte';
	import EmptyState from '../ui/EmptyState.svelte';

	/**
	 * @type {{
	 *   source?: 'tenant'|'public',
	 *   tenantId?: string,
	 *   providerId?: string,
	 *   slug?: string,
	 *   serviceId: string,
	 *   dateFrom: string,
	 *   dateTo: string,
	 *   locale?: 'en'|'ar',
	 *   selectedSlotId?: string|null,
	 *   onselect: (slot: import('../../api/booking.js').AvailableSlot) => void
	 * }}
	 */
	let {
		source = 'tenant',
		tenantId,
		providerId,
		slug,
		serviceId,
		dateFrom,
		dateTo,
		locale = 'en',
		selectedSlotId = null,
		onselect
	} = $props();

	let loading = $state(true);
	let error = $state(/** @type {string|null} */ (null));
	let slots = $state(/** @type {import('../../api/booking.js').AvailableSlot[]} */ ([]));

	$effect(() => {
		let cancelled = false;
		loading = true;
		error = null;

		const request =
			source === 'public'
				? getPublicAvailability(slug, serviceId, { dateFrom, dateTo }).then((r) => r.slots)
				: getAvailability(tenantId, { providerId, serviceId, dateFrom, dateTo }).then(
						(r) => r.items
					);

		request
			.then((items) => {
				if (!cancelled) slots = items;
			})
			.catch((err) => {
				if (!cancelled) error = err?.message ?? 'Could not load availability.';
			})
			.finally(() => {
				if (!cancelled) loading = false;
			});

		return () => {
			cancelled = true;
		};
	});

	let slotsByDay = $derived.by(() => {
		/** @type {Map<string, typeof slots>} */
		const groups = new Map();
		for (const slot of slots) {
			const day = formatDate(slot.starts_at, locale);
			groups.set(day, [...(groups.get(day) ?? []), slot]);
		}
		return groups;
	});
</script>

{#if loading}
	<div class="flex justify-center py-8"><Spinner /></div>
{:else if error}
	<Alert tone="error">{error}</Alert>
{:else if slots.length === 0}
	<EmptyState title="No free slots" description="Try a different date range or provider." />
{:else}
	<div class="flex flex-col gap-4">
		{#each slotsByDay as [day, daySlots] (day)}
			<div>
				<p class="mb-2 text-sm font-medium text-slate-700 dark:text-slate-200">{day}</p>
				<div class="flex flex-wrap gap-2">
					{#each daySlots as slot (slot.slot_id)}
						<button
							type="button"
							onclick={() => onselect(slot)}
							class={[
								'rounded-lg border px-3 py-1.5 text-sm transition-colors',
								slot.slot_id === selectedSlotId
									? 'border-rose-600 bg-rose-600 text-white'
									: 'border-slate-300 text-slate-700 hover:border-rose-400 dark:border-slate-700 dark:text-slate-200'
							].join(' ')}
						>
							{formatTime(slot.starts_at, locale)}
						</button>
					{/each}
				</div>
			</div>
		{/each}
	</div>
{/if}
