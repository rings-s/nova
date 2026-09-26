<script>
	import { t, tp, intlLocale } from '$lib/i18n/index.svelte.js';
	import Modal from '../ui/Modal.svelte';
	import Icon from '../ui/Icon.svelte';
	import Button from '../ui/Button.svelte';
	import TimeSlotList from './TimeSlotList.svelte';
	import { dayKeyToDate } from './availability.js';

	/**
	 * The times for one day, opened from a day on the full booking calendar.
	 * Previous / next step through the *bookable* days only, so the customer
	 * can compare neighbouring days without closing the modal. Picking a time
	 * hands it to `onselect`; the parent decides whether to close.
	 *
	 * @type {{
	 *   open: boolean,
	 *   dayKey: string|null,
	 *   slotsByDay: Map<string, import('./availability.js').Slot[]>,
	 *   selectedSlotId?: string|null,
	 *   subtitle?: string|null,
	 *   onselect: (slot: import('./availability.js').Slot) => void,
	 *   onchangeday: (key: string) => void,
	 *   onclose: () => void
	 * }}
	 */
	let {
		open,
		dayKey,
		slotsByDay,
		selectedSlotId = null,
		subtitle = null,
		onselect,
		onchangeday,
		onclose
	} = $props();

	let dayKeys = $derived([...slotsByDay.keys()].sort());
	let index = $derived(dayKey ? dayKeys.indexOf(dayKey) : -1);
	let prevKey = $derived(index > 0 ? dayKeys[index - 1] : null);
	let nextKey = $derived(index >= 0 && index < dayKeys.length - 1 ? dayKeys[index + 1] : null);
	let slots = $derived(dayKey ? (slotsByDay.get(dayKey) ?? []) : []);

	/** @param {string} key @param {Intl.DateTimeFormatOptions} options */
	function formatDay(key, options) {
		return new Intl.DateTimeFormat(intlLocale(), { ...options, timeZone: 'UTC' }).format(
			dayKeyToDate(key)
		);
	}

	let title = $derived(
		dayKey ? formatDay(dayKey, { weekday: 'long', day: 'numeric', month: 'long' }) : ''
	);
</script>

<Modal {open} {title} description={subtitle} {onclose}>
	<div
		class="mb-5 flex items-center justify-between gap-2 rounded-control border border-line bg-surface-sunken p-1"
	>
		<Button
			variant="ghost"
			size="sm"
			disabled={!prevKey}
			onclick={() => prevKey && onchangeday(prevKey)}
			aria-label={t('Previous available day')}
		>
			<Icon name="chevron-left" class="size-4 rtl:rotate-180" />
			<span class="hidden sm:inline">
				{prevKey ? formatDay(prevKey, { weekday: 'short', day: 'numeric' }) : t('Earlier')}
			</span>
		</Button>
		<p class="text-xs font-medium text-fg-muted tabular-nums">
			{tp(slots.length, '{count} time available', '{count} times available')}
		</p>
		<Button
			variant="ghost"
			size="sm"
			disabled={!nextKey}
			onclick={() => nextKey && onchangeday(nextKey)}
			aria-label={t('Next available day')}
		>
			<span class="hidden sm:inline">
				{nextKey ? formatDay(nextKey, { weekday: 'short', day: 'numeric' }) : t('Later')}
			</span>
			<Icon name="chevron-right" class="size-4 rtl:rotate-180" />
		</Button>
	</div>

	{#key dayKey}
		<div class="animate-fade-in">
			<TimeSlotList {slots} {selectedSlotId} showProvider {onselect} />
		</div>
	{/key}
</Modal>
