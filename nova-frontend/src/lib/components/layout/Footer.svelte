<script>
	import { t, m } from '$lib/i18n/index.svelte.js';
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import Logo from './Logo.svelte';

	const year = new Date().getFullYear();

	/** @typedef {{ label: string, href: '/features'|'/pricing'|'/discover'|'/about'|'/app'|'/bookings'|'/login'|'/register' }} FooterLink */

	/** @type {FooterLink[]} */
	const productLinks = [
		{ label: m('Features'), href: '/features' },
		{ label: m('Pricing'), href: '/pricing' },
		{ label: m('Book a treatment'), href: '/discover' },
		{ label: m('About'), href: '/about' }
	];

	/** @type {FooterLink[]} */
	let accountLinks = $derived(
		authStore.isAuthenticated
			? authStore.isStaff
				? [{ label: m('Dashboard'), href: '/app' }]
				: [{ label: m('My bookings'), href: '/bookings' }]
			: [
					{ label: m('Sign in'), href: '/login' },
					{ label: m('Sign up'), href: '/register' }
				]
	);

	/** @type {{ title: string, links: FooterLink[] }[]} */
	let columns = $derived([
		{ title: m('Product'), links: productLinks },
		{ title: m('Account'), links: accountLinks }
	]);
</script>

<footer class="border-t border-line bg-canvas">
	<div class="mx-auto w-full max-w-7xl px-5 sm:px-8">
		<div class="flex flex-col gap-10 py-12 sm:flex-row sm:justify-between">
			<div class="max-w-xs">
				<Logo />
				<p class="mt-4 text-sm leading-6 text-fg-muted">
					{t('Bookings, walk-ins and payments for salons, spas, massage centres and beauty clinics in the GCC.')}
				</p>
			</div>

			<div class="grid grid-cols-2 gap-10 sm:gap-16">
				{#each columns as column (column.title)}
					<nav aria-label={t(column.title)}>
						<h3 class="text-xs font-semibold tracking-wider text-fg uppercase">
							{t(column.title)}
						</h3>
						<ul class="mt-4 space-y-2.5">
							{#each column.links as link (link.href)}
								<li>
									<a
										href={resolve(link.href)}
										class="text-sm text-fg-muted transition-colors hover:text-fg"
									>
										{t(link.label)}
									</a>
								</li>
							{/each}
						</ul>
					</nav>
				{/each}
			</div>
		</div>

		<p class="border-t border-line py-6 text-xs text-fg-subtle">
			{t('© {year} NOVA. All rights reserved.', { year })}
		</p>
	</div>
</footer>
