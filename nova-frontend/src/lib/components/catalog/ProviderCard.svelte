<script>
	import { pickBilingual } from '../../utils/bilingual.js';
	import Card from '../ui/Card.svelte';
	import Avatar from '../ui/Avatar.svelte';

	/**
	 * @type {{
	 *   provider: import('../../api/catalog.js').Provider,
	 *   locale?: 'en'|'ar',
	 *   selected?: boolean,
	 *   onselect?: (provider: import('../../api/catalog.js').Provider) => void
	 * }}
	 */
	let { provider, locale = 'en', selected = false, onselect } = $props();

	let name = $derived(pickBilingual(provider, 'name', locale));
	let title = $derived(pickBilingual(provider, 'title', locale));
</script>

<button type="button" class="block w-full text-start" onclick={() => onselect?.(provider)}>
	<Card padding="sm" class={`transition-colors ${selected ? 'ring-2 ring-rose-500' : ''}`}>
		<div class="flex items-center gap-3">
			<Avatar {name} size="sm" />
			<div>
				<p class="font-medium text-slate-900 dark:text-slate-100">{name}</p>
				{#if title}
					<p class="text-xs text-slate-500 dark:text-slate-400">{title}</p>
				{/if}
			</div>
		</div>
	</Card>
</button>
