<script>
	import { t, m } from '$lib/i18n/index.svelte.js';
	import { formatTime } from '../../utils/datetime.js';
	import { pickBilingual } from '../../utils/bilingual.js';
	import { PERIOD_ORDER, slotsByPeriod } from './availability.js';

	/**
	 * One day's times, grouped into morning / afternoon / evening. A public
	 * slot names its provider (the public route answers across every
	 * qualified provider, so two slots can share a time); `showProvider` puts
	 * that name under the time.
	 *
	 * @type {{
	 *   slots: import('./availability.js').Slot[],
	 *   selectedSlotId?: string|null,
	 *   showProvider?: boolean,
	 *   onselect: (slot: import('./availability.js').Slot) => void
	 * }}
	 */
	let { slots, selectedSlotId = null, showProvider = false, onselect } = $props();

	const PERIOD_LABELS = { morning: m('Morning'), afternoon: m('Afternoon'), evening: m('Evening') };

	let periods = $derived(slotsByPeriod(slots));
</script>

<div class="flex flex-col gap-5">
	{#each PERIOD_ORDER as period (period)}
		{#if periods[period].length > 0}
			<div>
				<p class="mb-2 text-[11px] font-semibold tracking-wider text-fg-subtle uppercase">
					{t(PERIOD_LABELS[period])}
				</p>
				<div
					class={showProvider ? 'grid grid-cols-2 gap-2 sm:grid-cols-3' : 'flex flex-wrap gap-2'}
				>
					{#each periods[period] as slot (slot.slot_id)}
						{@const selected = slot.slot_id === selectedSlotId}
						<button
							type="button"
							aria-pressed={selected}
							onclick={() => onselect(slot)}
							class={[
								'inline-flex rounded-control border font-medium tabular-nums focus-ring transition-[border-color,background-color,color] duration-fast',
								showProvider
									? 'min-h-14 flex-col items-start justify-center px-3 py-2 text-start'
									: 'h-9 items-center px-3.5 text-sm',
								selected
									? 'border-brand-600 bg-brand-600 text-white shadow-glow'
									: 'border-line-strong bg-surface text-fg hover:border-brand-400 hover:bg-accent-soft hover:text-accent'
							].join(' ')}
						>
							<span class={showProvider ? 'text-sm font-semibold' : ''}>
								{formatTime(slot.starts_at)}
								{#if 'remaining_capacity' in slot && slot.remaining_capacity <= 2}
									<span
										class={[
											'ms-1 text-xs',
											selected ? 'text-white/80' : 'text-amber-600 dark:text-amber-400'
										].join(' ')}
									>
										· {t('{count} left', { count: slot.remaining_capacity })}
									</span>
								{/if}
							</span>
							{#if showProvider && 'provider_name_en' in slot}
								<span
									class={[
										'mt-0.5 w-full truncate text-xs font-normal',
										selected ? 'text-white/80' : 'text-fg-muted'
									].join(' ')}
								>
									{pickBilingual(slot, 'provider_name')}
								</span>
							{/if}
						</button>
					{/each}
				</div>
			</div>
		{/if}
	{/each}
</div>
