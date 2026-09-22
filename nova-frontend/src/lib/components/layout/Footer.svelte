<script>
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import Logo from './Logo.svelte';

	const year = new Date().getFullYear();

	/** @typedef {{ label: string, href: '/features'|'/pricing'|'/discover'|'/about'|'/app'|'/bookings'|'/login'|'/register' }} FooterLink */

	/** @type {FooterLink[]} */
	const productLinks = [
		{ label: 'Features', href: '/features' },
		{ label: 'Pricing', href: '/pricing' },
		{ label: 'Find a salon', href: '/discover' },
		{ label: 'About', href: '/about' }
	];

	/** @type {FooterLink[]} */
	let accountLinks = $derived(
		authStore.isAuthenticated
			? authStore.isStaff
				? [{ label: 'Dashboard', href: '/app' }]
				: [{ label: 'My bookings', href: '/bookings' }]
			: [
					{ label: 'Sign in', href: '/login' },
					{ label: 'Sign up', href: '/register' }
				]
	);

	/** @type {{ title: string, links: FooterLink[] }[]} */
	let columns = $derived([
		{ title: 'Product', links: productLinks },
		{ title: 'Account', links: accountLinks }
	]);
</script>

<footer class="border-t border-line bg-canvas">
	<div class="mx-auto w-full max-w-7xl px-5 sm:px-8">
		<div class="flex flex-col gap-10 py-12 sm:flex-row sm:justify-between">
			<div class="max-w-xs">
				<Logo />
				<p class="mt-4 text-sm leading-6 text-fg-muted">
					Bookings, walk-ins and payments for salons and spas in the GCC.
				</p>
			</div>

			<div class="grid grid-cols-2 gap-10 sm:gap-16">
				{#each columns as column (column.title)}
					<nav aria-label={column.title}>
						<h3 class="text-xs font-semibold tracking-wider text-fg uppercase">{column.title}</h3>
						<ul class="mt-4 space-y-2.5">
							{#each column.links as link (link.href)}
								<li>
									<a
										href={resolve(link.href)}
										class="text-sm text-fg-muted transition-colors hover:text-fg"
									>
										{link.label}
									</a>
								</li>
							{/each}
						</ul>
					</nav>
				{/each}
			</div>
		</div>

		<p class="border-t border-line py-6 text-xs text-fg-subtle">
			© {year} NOVA. All rights reserved.
		</p>
	</div>
</footer>
