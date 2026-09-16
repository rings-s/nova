<script>
	/**
	 * The tenant dashboard's section nav. A row of scrollable tabs on narrow
	 * screens, a fixed sidebar from `lg` up — one nav, two layouts, rather than
	 * a hamburger hiding it below a breakpoint.
	 */
	import { page } from '$app/state';
	import { resolve } from '$app/paths';

	const items =
		/** @type {{ href: '/app'|'/app/catalog'|'/app/bookings'|'/app/queue'|'/app/customers'|'/app/analytics'|'/app/billing'|'/app/team', label: string }[]} */ ([
			{ href: '/app', label: 'Overview' },
			{ href: '/app/catalog', label: 'Catalog' },
			{ href: '/app/bookings', label: 'Bookings' },
			{ href: '/app/queue', label: 'Queue' },
			{ href: '/app/customers', label: 'Customers' },
			{ href: '/app/analytics', label: 'Analytics' },
			{ href: '/app/billing', label: 'Billing' },
			{ href: '/app/team', label: 'Team' }
		]);

	let current = $derived(page.url.pathname);

	/**
	 * `/app` itself must match exactly — it's a prefix of every other item too.
	 * @param {string} href
	 */
	function isActive(href) {
		return href === '/app' ? current === href : current === href || current.startsWith(`${href}/`);
	}
</script>

<nav
	class="flex gap-1 overflow-x-auto border-b border-slate-200 pb-2 lg:w-48 lg:flex-col lg:overflow-visible lg:border-e lg:border-b-0 lg:pe-4 lg:pb-0 dark:border-slate-800"
>
	{#each items as item (item.href)}
		<a
			href={resolve(item.href)}
			class={[
				'shrink-0 rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors',
				isActive(item.href)
					? 'bg-brand-50 text-brand-700 dark:bg-brand-950/30 dark:text-brand-300'
					: 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
			].join(' ')}
		>
			{item.label}
		</a>
	{/each}
</nav>
