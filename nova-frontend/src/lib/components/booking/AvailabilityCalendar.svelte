<script>
	import { t, tp, intlLocale } from '$lib/i18n/index.svelte.js';
	import Icon from '../ui/Icon.svelte';
	import { iconButton } from '../ui/styles.js';
	import { dateKey, shortWeekdayLabel } from '../../utils/datetime.js';
	import { monthCells, monthKey, monthsBetween } from './availability.js';

	/**
	 * A month calendar of bookable days. Days with nothing bookable, or
	 * outside `fromKey`..`toKey`, are disabled.
	 *
	 * - `compact` (inside SlotPicker): one month at a time with paging, a dot
	 *   under each bookable day.
	 * - `full` (the booking page): every month the range touches, side by side
	 *   on wide screens, each bookable day showing how many times it has.
	 *
	 * @type {{
	 *   slotsByDay: Map<string, unknown[]>,
	 *   fromKey: string,
	 *   toKey: string,
	 *   selectedDayKey?: string|null,
	 *   variant?: 'compact'|'full',
	 *   onselectday: (key: string) => void
	 * }}
	 */
	let {
		slotsByDay,
		fromKey,
		toKey,
		selectedDayKey = null,
		variant = 'compact',
		onselectday
	} = $props();

	const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6];
	const todayKey = dateKey(new Date());

	// Compact paging: the displayed month follows the selected day (or the
	// range start), so reopening on an earlier choice lands on its page.
	let viewYear = $state(0);
	let viewMonth = $state(0);

	$effect(() => {
		const key = selectedDayKey ?? fromKey;
		if (!key) return;
		const [y, m] = key.split('-').map(Number);
		viewYear = y;
		viewMonth = m - 1;
	});

	let canGoPrev = $derived(!!fromKey && monthKey(viewYear, viewMonth) > fromKey.slice(0, 7));
	let canGoNext = $derived(!!toKey && monthKey(viewYear, viewMonth) < toKey.slice(0, 7));

	/** @param {number} delta */
	function shiftMonth(delta) {
		const total = viewYear * 12 + viewMonth + delta;
		viewYear = Math.floor(total / 12);
		viewMonth = ((total % 12) + 12) % 12;
	}

	let months = $derived(
		variant === 'full' ? monthsBetween(fromKey, toKey) : [{ year: viewYear, month: viewMonth }]
	);

	/** @param {number} year @param {number} month */
	function monthLabel(year, month) {
		return new Intl.DateTimeFormat(intlLocale(), {
			month: 'long',
			year: 'numeric',
			timeZone: 'UTC'
		}).format(new Date(Date.UTC(year, month, 1)));
	}

	/** @param {string} key */
	function inRange(key) {
		return (!fromKey || key >= fromKey) && (!toKey || key <= toKey);
	}
</script>

{#snippet weekdayRow()}
	<div class="grid grid-cols-7 gap-1 text-center text-[11px] font-medium text-fg-subtle">
		{#each WEEKDAYS as weekday (weekday)}
			<div class={variant === 'full' ? 'pb-1' : ''}>{shortWeekdayLabel(weekday)}</div>
		{/each}
	</div>
{/snippet}

{#snippet grid(/** @type {number} */ year, /** @type {number} */ month)}
	<div class={['mt-1 grid grid-cols-7', variant === 'full' ? 'gap-1.5' : 'gap-1'].join(' ')}>
		{#each monthCells(year, month) as cell, i (cell?.key ?? `blank-${i}`)}
			{#if cell === null}
				<div></div>
			{:else}
				{@const count = slotsByDay.get(cell.key)?.length ?? 0}
				{@const bookable = count > 0 && inRange(cell.key)}
				{@const selected = cell.key === selectedDayKey}
				<button
					type="button"
					disabled={!bookable}
					aria-pressed={selected}
					aria-label={bookable
						? `${cell.day} — ${tp(count, '{count} time available', '{count} times available')}`
						: undefined}
					onclick={() => onselectday(cell.key)}
					class={[
						'relative flex flex-col items-center justify-center rounded-control tabular-nums focus-ring transition-[background-color,color,box-shadow,transform] duration-fast disabled:cursor-not-allowed',
						variant === 'full'
							? 'aspect-square gap-0.5 text-base sm:aspect-[5/4] sm:text-lg'
							: 'aspect-square text-sm',
						selected
							? 'bg-brand-600 font-semibold text-white shadow-glow'
							: bookable
								? variant === 'full'
									? 'border border-line bg-surface font-semibold text-fg hover:-translate-y-px hover:border-brand-400 hover:bg-accent-soft hover:text-accent hover:shadow-card'
									: 'font-medium text-fg hover:bg-accent-soft hover:text-accent'
								: inRange(cell.key)
									? 'text-fg-subtle/60'
									: 'text-fg-subtle/30',
						cell.key === todayKey && !selected ? 'ring-1 ring-brand-400 ring-inset' : ''
					].join(' ')}
				>
					{cell.day}
					{#if variant === 'full' && bookable}
						<!-- The count is a small pill: a label ("45 times") doesn't fit a
						     cell when two months sit side by side. The aria-label says it
						     in full, and the page's legend explains the pill. -->
						<span
							class={[
								'hidden min-w-5 rounded-full px-1.5 text-[10px] leading-4 font-semibold whitespace-nowrap sm:block',
								selected ? 'bg-white/20 text-white' : 'bg-accent-soft text-accent'
							].join(' ')}
						>
							{count}
						</span>
						<span
							class={[
								'size-1 rounded-full sm:hidden',
								selected ? 'bg-white/80' : 'bg-brand-500'
							].join(' ')}
						></span>
					{:else if bookable && !selected}
						<span class="absolute bottom-1 size-1 rounded-full bg-brand-500"></span>
					{/if}
				</button>
			{/if}
		{/each}
	</div>
{/snippet}

{#if variant === 'compact'}
	<div class="rounded-card border border-line bg-surface p-3 shadow-card">
		<div class="mb-3 flex items-center justify-between">
			<button
				type="button"
				disabled={!canGoPrev}
				onclick={() => shiftMonth(-1)}
				aria-label={t('Previous month')}
				class={`${iconButton} size-8 disabled:pointer-events-none disabled:opacity-30`}
			>
				<Icon name="chevron-left" class="size-4 rtl:rotate-180" />
			</button>
			<p class="text-sm font-semibold text-fg">{monthLabel(viewYear, viewMonth)}</p>
			<button
				type="button"
				disabled={!canGoNext}
				onclick={() => shiftMonth(1)}
				aria-label={t('Next month')}
				class={`${iconButton} size-8 disabled:pointer-events-none disabled:opacity-30`}
			>
				<Icon name="chevron-right" class="size-4 rtl:rotate-180" />
			</button>
		</div>
		{@render weekdayRow()}
		{@render grid(viewYear, viewMonth)}
	</div>
{:else}
	<div class={['grid gap-8', months.length > 1 ? 'md:grid-cols-2 md:gap-x-10' : ''].join(' ')}>
		{#each months as { year, month } (monthKey(year, month))}
			<section aria-label={monthLabel(year, month)}>
				<h3 class="mb-3 text-sm font-semibold tracking-tight text-fg">{monthLabel(year, month)}</h3>
				{@render weekdayRow()}
				{@render grid(year, month)}
			</section>
		{/each}
	</div>
{/if}
