<script>
	import { pickBilingual } from '../../utils/bilingual.js';
	import { formatMoney } from '../../utils/money.js';
	import Card from '../ui/Card.svelte';
	import Badge from '../ui/Badge.svelte';

	/**
	 * Renders either a tenant-side `Service` (catalog.js) or a public
	 * `StorefrontService` (discovery.js) — the two share every field this uses.
	 * @type {{
	 *   service: import('../../api/catalog.js').Service|import('../../api/discovery.js').StorefrontService,
	 *   locale?: 'en'|'ar',
	 *   selected?: boolean,
	 *   onselect?: (service: import('../../api/catalog.js').Service|import('../../api/discovery.js').StorefrontService) => void
	 * }}
	 */
	let { service, locale = 'en', selected = false, onselect } = $props();
</script>

<button type="button" class="block w-full text-start" onclick={() => onselect?.(service)}>
	<Card padding="sm" class={`transition-colors ${selected ? 'ring-2 ring-brand-500' : ''}`}>
		<div class="flex items-start justify-between gap-3">
			<div>
				<p class="font-medium text-slate-900 dark:text-slate-100">
					{pickBilingual(service, 'name', locale)}
				</p>
				{#if service.category}
					<p class="text-xs text-slate-500 dark:text-slate-400">{service.category}</p>
				{/if}
				{#if pickBilingual(service, 'description', locale)}
					<p class="mt-1 text-sm text-slate-600 dark:text-slate-300">
						{pickBilingual(service, 'description', locale)}
					</p>
				{/if}
			</div>
			<div class="flex flex-col items-end gap-1">
				<Badge tone="accent">{formatMoney(service.price, service.currency, locale)}</Badge>
				<span class="text-xs text-slate-500 dark:text-slate-400"
					>{service.duration_minutes} min</span
				>
			</div>
		</div>
	</Card>
</button>
