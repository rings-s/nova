<script>
	/**
	 * The app shell's top bar. Anonymous visitors see sign-in/sign-up; a
	 * signed-in caller sees their tenant switcher (if they belong to any) and
	 * a sign-out control. Wraps rather than hides at narrow widths — there are
	 * few enough controls that a hamburger menu would be one more tap for
	 * nothing.
	 *
	 * Branches on route: `/app` and `/demo` keep this exact markup, byte for
	 * byte, since the dashboard redesign is a separate later phase. Every
	 * other route gets the redesigned public/marketing header (brand mark,
	 * Features/Pricing/About nav, sticky frosted bar).
	 */
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { authStore } from '../../stores/auth.svelte.js';
	import { toastStore } from '../../stores/toast.svelte.js';
	import { isPublicChromeRoute } from '../../utils/routeChrome.js';
	import Button from '../ui/Button.svelte';
	import TenantSwitcher from '../tenant/TenantSwitcher.svelte';
	import Logo from './Logo.svelte';

	async function handleSignOut() {
		authStore.logout();
		toastStore.info('Signed out.');
		await goto(resolve('/'));
	}

	let isPublic = $derived(isPublicChromeRoute(page.url.pathname));
</script>

{#if isPublic}
	<header
		class="sticky top-0 z-40 border-b border-slate-200/70 bg-white/80 backdrop-blur-md dark:border-slate-800/70 dark:bg-slate-950/70"
	>
		<div
			class="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8"
		>
			<div class="flex items-center gap-6">
				<a href={resolve('/')}><Logo /></a>
				<nav class="hidden items-center gap-5 sm:flex">
					<a
						href={resolve('/features')}
						class="text-sm font-medium text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100"
					>
						Features
					</a>
					<a
						href={resolve('/pricing')}
						class="text-sm font-medium text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100"
					>
						Pricing
					</a>
					<a
						href={resolve('/about')}
						class="text-sm font-medium text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100"
					>
						About
					</a>
					<a
						href={resolve('/discover')}
						class="text-sm font-medium text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100"
					>
						Find a salon
					</a>
				</nav>
				{#if authStore.isAuthenticated && !authStore.isStaff}
					<a
						href={resolve('/bookings')}
						class="hidden text-sm font-medium text-slate-600 hover:text-slate-900 sm:inline dark:text-slate-300 dark:hover:text-slate-100"
					>
						My bookings
					</a>
				{/if}
				{#if authStore.isStaff}
					<a
						href={resolve('/app')}
						class="hidden text-sm font-medium text-slate-600 hover:text-slate-900 sm:inline dark:text-slate-300 dark:hover:text-slate-100"
					>
						Dashboard
					</a>
				{/if}
			</div>

			<div class="flex flex-wrap items-center gap-3">
				{#if authStore.isAuthenticated}
					{#if authStore.isStaff}
						<div class="w-40 sm:w-48">
							<TenantSwitcher />
						</div>
					{/if}
					<Button variant="ghost" size="sm" onclick={handleSignOut}>Sign out</Button>
				{:else}
					<Button variant="ghost" size="sm" href={resolve('/login')}>Sign in</Button>
					<Button size="sm" href={resolve('/register')}>Sign up</Button>
				{/if}
			</div>
		</div>
	</header>
{:else}
	<header class="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
		<div
			class="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6"
		>
			<div class="flex items-center gap-4">
				<a href={resolve('/')} class="text-lg font-semibold text-slate-900 dark:text-slate-100"
					>NOVA</a
				>
				<a
					href={resolve('/discover')}
					class="text-sm font-medium text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100"
				>
					Find a salon
				</a>
				{#if authStore.isAuthenticated && !authStore.isStaff}
					<a
						href={resolve('/bookings')}
						class="text-sm font-medium text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100"
					>
						My bookings
					</a>
				{/if}
				{#if authStore.isStaff}
					<a
						href={resolve('/app')}
						class="text-sm font-medium text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100"
					>
						Dashboard
					</a>
				{/if}
			</div>

			<div class="flex flex-wrap items-center gap-3">
				{#if authStore.isAuthenticated}
					{#if authStore.isStaff}
						<div class="w-40 sm:w-48">
							<TenantSwitcher />
						</div>
					{/if}
					<Button variant="ghost" size="sm" onclick={handleSignOut}>Sign out</Button>
				{:else}
					<Button variant="ghost" size="sm" href={resolve('/login')}>Sign in</Button>
					<Button size="sm" href={resolve('/register')}>Sign up</Button>
				{/if}
			</div>
		</div>
	</header>
{/if}
