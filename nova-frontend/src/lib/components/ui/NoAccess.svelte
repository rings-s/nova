<script>
	import EmptyState from './EmptyState.svelte';
	import Icon from './Icon.svelte';

	/**
	 * Shown in place of a page the caller's role in this business can't open,
	 * reached by URL rather than from the (already filtered) sidebar.
	 *
	 * @type {{ who?: string, what?: string }}
	 */
	let { who = 'owners and managers', what = 'this page' } = $props();
</script>

<EmptyState
	title="You don't have access to {what}"
	description="Only {who} of this business can open it. Ask your owner if you need access."
>
	{#snippet icon()}<Icon name="shield-check" class="size-6" />{/snippet}
</EmptyState>
