<script>
	/**
	 * The tenant dashboard's section nav, grouped by job: the day-to-day
	 * operating screens first, then the ones that set the business up. The
	 * same list renders in the desktop sidebar and the mobile drawer.
	 */
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import Icon from '../ui/Icon.svelte';
	import { accessStore } from '../../stores/access.svelte.js';

	/** @type {{ onnavigate?: () => void }} */
	let { onnavigate } = $props();

	/**
	 * @typedef {'/app'|'/app/catalog'|'/app/bookings'|'/app/queue'|'/app/customers'|'/app/reviews'|'/app/analytics'|'/app/billing'|'/app/team'} AppHref
	 * @type {{ label: string, items: { href: AppHref, label: string, icon: import('../ui/Icon.svelte').IconName, needs?: import('../../api/identity.js').StaffPermission }[] }[]}
	 */
	const groups = [
		{
			label: 'Operate',
			items: [
				{ href: '/app', label: 'Overview', icon: 'home' },
				{ href: '/app/bookings', label: 'Bookings', icon: 'calendar' },
				{ href: '/app/queue', label: 'Walk-in queue', icon: 'users' },
				{ href: '/app/customers', label: 'Customers', icon: 'user' }
			]
		},
		{
			label: 'Business',
			items: [
				{ href: '/app/catalog', label: 'Catalog', icon: 'layers' },
				{ href: '/app/reviews', label: 'Reviews', icon: 'star' },
				{ href: '/app/analytics', label: 'Analytics', icon: 'chart-bar', needs: 'view_analytics' },
				{ href: '/app/billing', label: 'Billing', icon: 'credit-card', needs: 'view_financials' },
				{ href: '/app/team', label: 'Team', icon: 'user-check' }
			]
		}
	];

	let current = $derived(page.url.pathname);

	// Only the pages this role can use in this business. A link that can only
	// ever answer "not allowed" is noise; the server still guards each page.
	let visibleGroups = $derived(
		groups.map((group) => ({
			...group,
			items: group.items.filter((item) => !item.needs || accessStore.can(item.needs))
		}))
	);

	/**
	 * `/app` itself must match exactly — it's a prefix of every other item too.
	 * @param {string} href
	 */
	function isActive(href) {
		return href === '/app' ? current === href : current === href || current.startsWith(`${href}/`);
	}
</script>

<nav class="flex flex-col gap-6" aria-label="Dashboard">
	{#each visibleGroups as group (group.label)}
		<div>
			<p class="mb-1.5 px-3 text-[11px] font-semibold tracking-wider text-fg-subtle uppercase">
				{group.label}
			</p>
			<ul class="flex flex-col gap-0.5">
				{#each group.items as item (item.href)}
					{@const active = isActive(item.href)}
					<li>
						<a
							href={resolve(item.href)}
							onclick={onnavigate}
							aria-current={active ? 'page' : undefined}
							class={[
								'group relative flex h-9 items-center gap-3 rounded-control px-3 text-sm font-medium',
								'duration-fast focus-ring transition-colors',
								active
									? 'bg-surface text-fg shadow-card ring-1 ring-line dark:bg-surface-muted/70 dark:ring-white/5'
									: 'text-fg-muted hover:bg-surface-muted/70 hover:text-fg'
							].join(' ')}
						>
							{#if active}
								<span
									class="absolute inset-y-2 -start-3 w-[3px] rounded-e-full bg-brand-500"
									aria-hidden="true"
								></span>
							{/if}
							<Icon
								name={item.icon}
								class={`size-[18px] shrink-0 ${active ? 'text-accent' : 'text-fg-subtle group-hover:text-fg-muted'}`}
							/>
							{item.label}
						</a>
					</li>
				{/each}
			</ul>
		</div>
	{/each}
</nav>
