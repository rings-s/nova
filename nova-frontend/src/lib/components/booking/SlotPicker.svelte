<script>
	/**
	 * Fetches and renders bookable slots for one provider/service pair. Works
	 * against either the authenticated `getAvailability` (booking.js) or the
	 * public `getPublicAvailability` (discovery.js) — pass `source` to pick.
	 *
	 * A month calendar picks the day (days with nothing bookable are disabled,
	 * days with something get a dot), and the times for the selected day are
	 * grouped by morning/afternoon/evening below it. Calendar cells are built
	 * from plain `{year, month, day}` arithmetic rather than by formatting a
	 * `Date` through a timezone — the grid's weekday layout is calendar math,
	 * timezone-invariant, and mixing the two risks a cell landing on the wrong
	 * day for a viewer far from Asia/Riyadh (see `dateKey` in datetime.js,
	 * which *is* timezone-aware, for matching slots to the day they fall on
	 * in the salon's own clock).
	 */
	import { getAvailability } from '../../api/booking.js';
	import { getPublicAvailability } from '../../api/discovery.js';
	import {
		formatTime,
		dateKey,
		DEFAULT_TIMEZONE,
		shortWeekdayLabel
	} from '../../utils/datetime.js';
	import Spinner from '../ui/Spinner.svelte';
	import Alert from '../ui/Alert.svelte';
	import EmptyState from '../ui/EmptyState.svelte';
	import { errorMessage } from '../../utils/errors.js';
	import { SvelteMap } from 'svelte/reactivity';

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
	 *   onselect: (slot: import('../../api/booking.js').AvailableSlot|import('../../api/discovery.js').PublicSlot) => void
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
	let slots = $state(
		/** @type {(import('../../api/booking.js').AvailableSlot|import('../../api/discovery.js').PublicSlot)[]} */ ([])
	);

	$effect(() => {
		let cancelled = false;
		loading = true;
		error = null;

		// `slug` (public) and `tenantId` (tenant) are each required only for the
		// branch that uses them — the caller picks one via `source`.
		const request =
			source === 'public'
				? getPublicAvailability(/** @type {string} */ (slug), serviceId, { dateFrom, dateTo }).then(
						(r) => r.slots
					)
				: getAvailability(/** @type {string} */ (tenantId), {
						providerId: /** @type {string} */ (providerId),
						serviceId,
						dateFrom,
						dateTo
					}).then((r) => r.items);

		request
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

	let slotsByDay = $derived.by(() => {
		/** @type {SvelteMap<string, typeof slots>} */
		const groups = new SvelteMap();
		for (const slot of slots) {
			const key = dateKey(slot.starts_at);
			groups.set(key, [...(groups.get(key) ?? []), slot]);
		}
		return groups;
	});

	let fromKey = $derived(dateFrom ? dateKey(dateFrom) : '');
	let toKey = $derived(dateTo ? dateKey(dateTo) : '');
	let todayKey = dateKey(new Date());

	// The day selected on the calendar. Defaults to the day of an
	// already-selected slot (reopening on a previous choice), else the first
	// day that actually has something bookable.
	let selectedDayKey = $state(/** @type {string|null} */ (null));

	$effect(() => {
		if (selectedSlotId) {
			const owning = slots.find((s) => s.slot_id === selectedSlotId);
			if (owning) {
				selectedDayKey = dateKey(owning.starts_at);
				return;
			}
		}
		selectedDayKey = [...slotsByDay.keys()].sort()[0] ?? null;
	});

	// The calendar's displayed month, kept in step with `selectedDayKey` so
	// picking a day (or loading with one preselected) always opens on the
	// right page.
	let viewYear = $state(0);
	let viewMonth = $state(0);

	$effect(() => {
		const key = selectedDayKey ?? fromKey;
		if (!key) return;
		const [y, m] = key.split('-').map(Number);
		viewYear = y;
		viewMonth = m - 1;
	});

	/** @param {number} year @param {number} month 0-indexed */
	function monthKey(year, month) {
		return `${year}-${String(month + 1).padStart(2, '0')}`;
	}

	let canGoPrevMonth = $derived(!!fromKey && monthKey(viewYear, viewMonth) > fromKey.slice(0, 7));
	let canGoNextMonth = $derived(!!toKey && monthKey(viewYear, viewMonth) < toKey.slice(0, 7));

	/** @param {number} delta */
	function shiftMonth(delta) {
		const total = viewYear * 12 + viewMonth + delta;
		viewYear = Math.floor(total / 12);
		viewMonth = ((total % 12) + 12) % 12;
	}

	let monthLabel = $derived(
		new Intl.DateTimeFormat(locale === 'ar' ? 'ar-SA' : 'en-US', {
			month: 'long',
			year: 'numeric'
		}).format(new Date(viewYear, viewMonth, 1))
	);

	/**
	 * @typedef {{ key: string, day: number, inRange: boolean, hasSlots: boolean, isToday: boolean }} CalendarCell
	 */
	let calendarCells = $derived.by(() => {
		const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
		// JS getDay() is Sunday=0..Saturday=6; the rest of this app is
		// Monday-first (booking.js's WorkingWindow, the schedule editor), so
		// rotate to Monday=0..Sunday=6 for a matching calendar layout.
		const leadingBlanks = (new Date(viewYear, viewMonth, 1).getDay() + 6) % 7;

		/** @type {(CalendarCell|null)[]} */
		const cells = Array.from({ length: leadingBlanks }, () => null);
		for (let day = 1; day <= daysInMonth; day++) {
			const key = `${viewYear}-${String(viewMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
			cells.push({
				key,
				day,
				inRange: (!fromKey || key >= fromKey) && (!toKey || key <= toKey),
				hasSlots: slotsByDay.has(key),
				isToday: key === todayKey
			});
		}
		return cells;
	});

	let selectedDaySlots = $derived(selectedDayKey ? (slotsByDay.get(selectedDayKey) ?? []) : []);

	const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6, 7];

	const PERIOD_ORDER = /** @type {const} */ (['morning', 'afternoon', 'evening']);
	const PERIOD_LABELS = {
		en: { morning: 'Morning', afternoon: 'Afternoon', evening: 'Evening' },
		ar: { morning: 'صباحًا', afternoon: 'ظهرًا', evening: 'مساءً' }
	};

	/** @param {string} iso */
	function periodOf(iso) {
		const hour = Number(
			new Intl.DateTimeFormat('en-US', {
				timeZone: DEFAULT_TIMEZONE,
				hour: 'numeric',
				hour12: false
			}).format(new Date(iso))
		);
		if (hour < 12) return 'morning';
		if (hour < 17) return 'afternoon';
		return 'evening';
	}

	let periods = $derived.by(() => {
		/** @type {Record<typeof PERIOD_ORDER[number], typeof slots>} */
		const buckets = { morning: [], afternoon: [], evening: [] };
		for (const slot of selectedDaySlots) buckets[periodOf(slot.starts_at)].push(slot);
		return buckets;
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
		<div class="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
			<div class="mb-2 flex items-center justify-between">
				<button
					type="button"
					disabled={!canGoPrevMonth}
					onclick={() => shiftMonth(-1)}
					aria-label="Previous month"
					class="rounded-md p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30 disabled:hover:bg-transparent dark:text-slate-400 dark:hover:bg-slate-800"
				>
					<svg class="size-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
						<path
							fill-rule="evenodd"
							d="M12.79 5.23a.75.75 0 010 1.06L9.06 10l3.73 3.71a.75.75 0 11-1.06 1.06l-4.25-4.25a.75.75 0 010-1.06l4.25-4.25a.75.75 0 011.06 0z"
							clip-rule="evenodd"
						/>
					</svg>
				</button>
				<p class="text-sm font-medium text-slate-900 dark:text-slate-100">{monthLabel}</p>
				<button
					type="button"
					disabled={!canGoNextMonth}
					onclick={() => shiftMonth(1)}
					aria-label="Next month"
					class="rounded-md p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30 disabled:hover:bg-transparent dark:text-slate-400 dark:hover:bg-slate-800"
				>
					<svg class="size-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
						<path
							fill-rule="evenodd"
							d="M7.21 14.77a.75.75 0 010-1.06L10.94 10 7.21 6.29a.75.75 0 111.06-1.06l4.25 4.25a.75.75 0 010 1.06l-4.25 4.25a.75.75 0 01-1.06 0z"
							clip-rule="evenodd"
						/>
					</svg>
				</button>
			</div>

			<div class="grid grid-cols-7 gap-1 text-center text-xs text-slate-400 dark:text-slate-500">
				{#each WEEKDAYS as weekday (weekday)}
					<div>{shortWeekdayLabel(weekday, locale)}</div>
				{/each}
			</div>
			<div class="mt-1 grid grid-cols-7 gap-1">
				{#each calendarCells as cell, i (cell?.key ?? `blank-${i}`)}
					{#if cell === null}
						<div></div>
					{:else}
						<button
							type="button"
							disabled={!cell.inRange || !cell.hasSlots}
							aria-pressed={cell.key === selectedDayKey}
							onclick={() => (selectedDayKey = cell.key)}
							class={[
								'relative flex aspect-square flex-col items-center justify-center rounded-lg text-sm transition-colors disabled:cursor-not-allowed',
								cell.key === selectedDayKey
									? 'bg-brand-600 font-medium text-white'
									: cell.hasSlots
										? 'text-slate-700 hover:bg-brand-50 dark:text-slate-200 dark:hover:bg-brand-950/30'
										: 'text-slate-300 dark:text-slate-700',
								cell.isToday && cell.key !== selectedDayKey
									? 'ring-1 ring-brand-400 ring-inset'
									: ''
							].join(' ')}
						>
							{cell.day}
							{#if cell.hasSlots && cell.key !== selectedDayKey}
								<span class="absolute bottom-1 size-1 rounded-full bg-brand-500"></span>
							{/if}
						</button>
					{/if}
				{/each}
			</div>
		</div>

		{#if selectedDaySlots.length === 0}
			<EmptyState
				title="Nothing free this day"
				description="Pick a highlighted day on the calendar."
			/>
		{:else}
			<div class="flex flex-col gap-4">
				{#each PERIOD_ORDER as period (period)}
					{#if periods[period].length > 0}
						<div>
							<p
								class="mb-2 text-xs font-medium tracking-wide text-slate-500 uppercase dark:text-slate-400"
							>
								{PERIOD_LABELS[locale]?.[period] ?? PERIOD_LABELS.en[period]}
							</p>
							<div class="flex flex-wrap gap-2">
								{#each periods[period] as slot (slot.slot_id)}
									<button
										type="button"
										onclick={() => onselect(slot)}
										class={[
											'rounded-lg border px-3 py-1.5 text-sm transition-colors',
											slot.slot_id === selectedSlotId
												? 'border-brand-600 bg-brand-600 text-white'
												: 'border-slate-300 text-slate-700 hover:border-brand-400 dark:border-slate-700 dark:text-slate-200'
										].join(' ')}
									>
										{formatTime(slot.starts_at, locale)}
										{#if 'remaining_capacity' in slot && slot.remaining_capacity <= 2}
											<span
												class={[
													'ms-1 text-xs',
													slot.slot_id === selectedSlotId
														? 'text-white/80'
														: 'text-amber-600 dark:text-amber-400'
												].join(' ')}
											>
												· {slot.remaining_capacity} left
											</span>
										{/if}
									</button>
								{/each}
							</div>
						</div>
					{/if}
				{/each}
			</div>
		{/if}
	</div>
{/if}
