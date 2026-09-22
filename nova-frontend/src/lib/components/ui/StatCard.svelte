<script>
	import Icon from './Icon.svelte';
	import Skeleton from './Skeleton.svelte';

	/**
	 * One headline number with its label and a line of context.
	 *
	 * @type {{
	 *   label: string,
	 *   value: string|number,
	 *   hint?: string|null,
	 *   icon?: import('./Icon.svelte').IconName|null,
	 *   loading?: boolean,
	 *   href?: string|null
	 * }}
	 */
	let { label, value, hint = null, icon = null, loading = false, href = null } = $props();
</script>

<svelte:element
	this={href ? 'a' : 'div'}
	{href}
	class={[
		'group relative flex flex-col rounded-card border border-line bg-surface p-5 shadow-card',
		href
			? 'duration-base focus-ring transition-[border-color,box-shadow] ease-out-premium hover:border-line-strong hover:shadow-raised'
			: ''
	].join(' ')}
>
	<div class="flex items-center justify-between gap-3">
		<span class="text-[13px] font-medium text-fg-muted">{label}</span>
		{#if icon}
			<span
				class="flex size-8 items-center justify-center rounded-control bg-accent-soft text-accent"
			>
				<Icon name={icon} class="size-4" />
			</span>
		{/if}
	</div>
	{#if loading}
		<Skeleton class="mt-3 h-8 w-16" />
	{:else}
		<p class="mt-2 text-3xl font-semibold tracking-tight text-fg tabular-nums">{value}</p>
	{/if}
	{#if hint}
		<p class="mt-1 text-xs text-fg-muted">{hint}</p>
	{/if}
</svelte:element>
