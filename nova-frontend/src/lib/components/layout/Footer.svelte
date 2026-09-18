
<script>
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import Logo from './Logo.svelte';

	const year = new Date().getFullYear();

	const productLinks = [
		{ label: 'Features', href: '/features' },
		{ label: 'Pricing', href: '/pricing' },
		{ label: 'Find a salon', href: '/discover' }
	];

	const companyLinks = [
		{ label: 'About', href: '/about' }
	];

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
</script>

<footer
	class="border-t border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950"
>
	<div class="mx-auto w-full max-w-7xl px-5 sm:px-8">

		<!-- Main footer -->
		<div class="grid gap-12 py-16 lg:grid-cols-[1.5fr_1fr_1fr_1fr] lg:py-20">

			<!-- Brand -->
			<div class="max-w-sm">
				<Logo variant="mark" />

				<p
					class="mt-5 text-sm leading-6 text-slate-500 dark:text-slate-400"
				>
					A modern operating system for salons, beauty businesses,
					and their customers.
				</p>

				<div
					class="mt-6 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-medium text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400"
				>
					<span class="size-1.5 rounded-full bg-emerald-500"></span>
					Designed for modern salons
				</div>
			</div>

			<!-- Company -->
			<div>
				<h3
					class="text-xs font-bold uppercase tracking-widest text-slate-900 dark:text-slate-100"
				>
					Company
				</h3>

				<nav class="mt-5 space-y-3">
					{#each companyLinks as link}
						<a
							href={resolve(link.href)}
							class="block text-sm text-slate-500 transition-colors hover:text-slate-950 dark:text-slate-400 dark:hover:text-white"
						>
							{link.label}
						</a>
					{/each}
				</nav>
			</div>

			<!-- Product -->
			<div>
				<h3
					class="text-xs font-bold uppercase tracking-widest text-slate-900 dark:text-slate-100"
				>
					Product
				</h3>

				<nav class="mt-5 space-y-3">
					{#each productLinks as link}
						<a
							href={resolve(link.href)}
							class="block text-sm text-slate-500 transition-colors hover:text-slate-950 dark:text-slate-400 dark:hover:text-white"
						>
							{link.label}
						</a>
					{/each}
				</nav>
			</div>

			<!-- Account -->
			<div>
				<h3
					class="text-xs font-bold uppercase tracking-widest text-slate-900 dark:text-slate-100"
				>
					Account
				</h3>

				<nav class="mt-5 space-y-3">
					{#each accountLinks as link}
						<a
							href={resolve(link.href)}
							class="block text-sm text-slate-500 transition-colors hover:text-slate-950 dark:text-slate-400 dark:hover:text-white"
						>
							{link.label}
						</a>
					{/each}
				</nav>
			</div>
		</div>

		<!-- Bottom bar -->
		<div
			class="flex flex-col gap-4 border-t border-slate-200 py-7 dark:border-slate-800 sm:flex-row sm:items-center sm:justify-between"
		>
			<div class="flex items-center gap-4">
				<Logo variant="mark" />

				<span class="hidden h-4 w-px bg-slate-200 dark:bg-slate-800 sm:block"></span>

				<p class="text-xs text-slate-500 dark:text-slate-400">
					© {year} NOVA. All rights reserved.
				</p>
			</div>

			<p class="text-xs text-slate-400 dark:text-slate-500">
				Salon operations, simplified.
			</p>
		</div>
	</div>
</footer>
