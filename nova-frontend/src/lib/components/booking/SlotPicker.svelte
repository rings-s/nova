<script>
	import { t } from '$lib/i18n/index.svelte.js';
	import Icon from '../ui/Icon.svelte';
	/**
	 * Fetches and renders bookable slots for one provider/service pair, inline:
	 * a compact month calendar picks the day, and that day's times sit below
	 * it. For a surface that is already a modal (staff reschedule). The
	 * customer booking flow uses the full-page calendar with `TimeSlotModal`
	 * instead (`/discover/[slug]/book`).
	 *
	 * Pass `source` to pick the staff `getAvailability` or the public
	 * `getPublicAvailability` — see `fetchSlots` in availability.js.
	 */
	import { dateKey } from '../../utils/datetime.js';
	import Spinner from '../ui/Spinner.svelte';
	import Alert from '../ui/Alert.svelte';
	import EmptyState from '../ui/EmptyState.svelte';
	import { errorMessage } from '../../utils/errors.js';
	import AvailabilityCalendar from './AvailabilityCalendar.svelte';
	import TimeSlotList from './TimeSlotList.svelte';
	import { fetchSlots, groupSlotsByDay } from './availability.js';

	/**
	 * @type {{
	 *   source?: 'tenant'|'public',
	 *   tenantId?: string,
	 *   providerId?: string,
	 *   slug?: string,
	 *   serviceId: string,
	 *   dateFrom: string,
	 *   dateTo: string,
	 *   selectedSlotId?: string|null,
	 *   onselect: (slot: import('./availability.js').Slot) => void
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
		selectedSlotId = null,
		onselect
	} = $props();

	let loading = $state(true);
	let error = $state(/** @type {string|null} */ (null));
	let slots = $state(/** @type {import('./availability.js').Slot[]} */ ([]));

	$effect(() => {
		let cancelled = false;
		loading = true;
		error = null;

		fetchSlots({ source, tenantId, providerId, slug, serviceId, dateFrom, dateTo })
			.then((items) => {
				if (!cancelled) slots = items;
			})
			.catch((err) => {
				if (!cancelled) error = errorMessage(err);
			})
			.finally(() => {
				if (!cancelled) loading = false;
			});

		return () => {
			cancelled = true;
		};
	});

	let slotsByDay = $derived(groupSlotsByDay(slots));

	// Defaults to the day of an already-selected slot (reopening on a previous
	// choice), else the first day that actually has something bookable.
	let selectedDayKey = $state(/** @type {string|null} */ (null));

	$effect(() => {
		if (selectedSlotId) {
			const owning = slots.find((s) => s.slot_id === selectedSlotId);
			if (owning) {
				selectedDayKey = dateKey(owning.starts_at);
				return;
			}
		}
		selectedDayKey = [...slotsByDay.keys()][0] ?? null;
	});

	let selectedDaySlots = $derived(selectedDayKey ? (slotsByDay.get(selectedDayKey) ?? []) : []);
</script>

{#if loading}
	<div class="flex justify-center py-8"><Spinner /></div>
{:else if error}
	<Alert tone="error">{error}</Alert>
{:else if slots.length === 0}
	<EmptyState title={t('No free slots')} description={t('Try a different date range or provider.')}>
		{#snippet icon()}<Icon name="clock" class="size-6" />{/snippet}
	</EmptyState>
{:else}
	<div class="flex flex-col gap-4">
		<AvailabilityCalendar
			{slotsByDay}
			fromKey={dateKey(dateFrom)}
			toKey={dateKey(dateTo)}
			{selectedDayKey}
			onselectday={(key) => (selectedDayKey = key)}
		/>

		{#if selectedDaySlots.length === 0}
			<EmptyState
				title={t('Nothing free this day')}
				description={t('Pick a highlighted day on the calendar.')}
			/>
		{:else}
			<TimeSlotList slots={selectedDaySlots} {selectedSlotId} {onselect} />
		{/if}
	</div>
{/if}
