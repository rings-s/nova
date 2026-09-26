<script>
	import { t } from '$lib/i18n/index.svelte.js';
	import EmptyState from './EmptyState.svelte';
	import Icon from './Icon.svelte';

	/**
	 * Shown in place of a page the caller's role in this business can't open,
	 * reached by URL rather than from the (already filtered) sidebar.
	 *
	 * Both are already translated by the caller.
	 *
	 * @type {{ who?: string|null, what?: string|null }}
	 */
	let { who = null, what = null } = $props();
</script>

<EmptyState
	title={t("You don't have access to {what}", { what: what ?? t('this page') })}
	description={t('Only {who} of this business can open it. Ask your owner if you need access.', {
		who: who ?? t('owners and managers')
	})}
>
	{#snippet icon()}<Icon name="shield-check" class="size-6" />{/snippet}
</EmptyState>
