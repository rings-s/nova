<script>
	/**
	 * Switches between English and Arabic. It names the other language in that
	 * language ("العربية" / "English"), so it can be found by someone who
	 * cannot read the current one.
	 *
	 * @type {{ class?: string, compact?: boolean }}
	 */
	import { i18n, setLocale, t } from '$lib/i18n/index.svelte.js';
	import Icon from './Icon.svelte';

	let { class: className = '', compact = false } = $props();

	let target = $derived(/** @type {'en'|'ar'} */ (i18n.locale === 'ar' ? 'en' : 'ar'));
</script>

<button
	type="button"
	onclick={() => setLocale(target)}
	lang={target}
	aria-label={t('Switch language to {language}', {
		language: target === 'ar' ? 'العربية' : 'English'
	})}
	class={[
		'inline-flex h-10 items-center justify-center gap-1.5 rounded-control text-sm font-medium text-fg-secondary focus-ring transition-colors hover:bg-surface-muted hover:text-fg',
		compact ? 'w-10' : 'px-3',
		className
	].join(' ')}
>
	<Icon name="globe" class="size-4 shrink-0" />
	{#if !compact}
		<span>{target === 'ar' ? 'العربية' : 'English'}</span>
	{/if}
</button>
