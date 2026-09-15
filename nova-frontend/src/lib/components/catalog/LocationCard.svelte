<script>
	import { pickBilingual } from '../../utils/bilingual.js';
	import Card from '../ui/Card.svelte';

	/**
	 * @type {{ location: import('../../api/catalog.js').Location, locale?: 'en'|'ar' }}
	 */
	let { location, locale = 'en' } = $props();
</script>

<Card padding="sm">
	<p class="font-medium text-slate-900 dark:text-slate-100">
		{pickBilingual(location, 'name', locale)}
	</p>
	<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">
		{[location.city, location.phone].filter(Boolean).join(' · ')}
	</p>
	<p class="text-xs text-slate-400 dark:text-slate-500">{location.timezone}</p>
</Card>
