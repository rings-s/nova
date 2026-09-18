
<script>
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';

	import { authStore } from '../../stores/auth.svelte.js';
	import { toastStore } from '../../stores/toast.svelte.js';
	import { isPublicChromeRoute } from '../../utils/routeChrome.js';

	import Button from '../ui/Button.svelte';
	import Icon from '../ui/Icon.svelte';
	import ThemeToggle from '../ui/ThemeToggle.svelte';
	import TenantSwitcher from '../tenant/TenantSwitcher.svelte';
	import Logo from './Logo.svelte';

	let isPublic = $derived(isPublicChromeRoute(page.url.pathname));
	let mobileOpen = $state(false);

	$effect(() => {
		page.url.pathname;
		mobileOpen = false;
	});

	const publicNavLinks = [
		{ href: '/about', label: 'About' },
		{ href: '/features', label: 'Features' },
		{ href: '/pricing', label: 'Pricing' },
		{ href: '/discover', label: 'Find a salon' }
	];

	async function handleSignOut() {
		authStore.logout();
		toastStore.info('Signed out.');
		await goto(resolve('/'));
	}
</script>

{#if isPublic}
	<header
		class="sticky top-0 z-40 border-b border-slate-200/70 bg-white/85 backdrop-blur-xl dark:border-slate-800/70 dark:bg-slate-950/85"
	>
		<div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
			<div class="flex min-h-16 items-center justify-between gap-6">
				<!-- Brand -->
				<div class="flex min-w-0 items-center gap-8">
					<a
						href={resolve('/')}
						class="shrink-0 transition-opacity hover:opacity-80"
						aria-label="NOVA home"
					>
						<Logo />
					</a>

					<!-- Desktop navigation -->
					<nav class="hidden items-center gap-7 lg:flex" aria-label="Main navigation">
						{#each publicNavLinks as link (link.href)}
							<a
								href={resolve(link.href)}
								class="relative py-5 text-sm font-medium text-slate-600 transition-colors hover:text-slate-950 dark:text-slate-300 dark:hover:text-white"
							>
								{link.label}
							</a>
						{/each}
					</nav>

					<!-- Authenticated shortcuts -->
					{#if authStore.isAuthenticated}
						<div class="hidden h-5 w-px bg-slate-200 lg:block dark:bg-slate-800"></div>

						{#if authStore.isStaff}
							<a
								href={resolve('/app')}
								class="hidden text-sm font-semibold text-slate-700 transition-colors hover:text-slate-950 lg:block dark:text-slate-200 dark:hover:text-white"
							>
								Dashboard
							</a>
						{:else}
							<a
								href={resolve('/bookings')}
								class="hidden text-sm font-semibold text-slate-700 transition-colors hover:text-slate-950 lg:block dark:text-slate-200 dark:hover:text-white"
							>
								My bookings
							</a>
						{/if}
					{/if}
				</div>

				<!-- Desktop actions -->
				<div class="hidden items-center gap-2 sm:flex">
					<ThemeToggle />

					<div class="mx-1 h-6 w-px bg-slate-200 dark:bg-slate-800"></div>

					{#if authStore.isAuthenticated}
						{#if authStore.isStaff}
							<div class="w-44">
								<TenantSwitcher />
							</div>
						{/if}

						<Button
							variant="ghost"
							size="sm"
							onclick={handleSignOut}
							class="text-slate-600 dark:text-slate-300"
						>
							Sign out
						</Button>
					{:else}
						<Button
							variant="ghost"
							size="sm"
							href={resolve('/login')}
						>
							Sign in
						</Button>

						<Button size="sm" href={resolve('/register')}>
							Get started
						</Button>
					{/if}
				</div>

				<!-- Mobile controls -->
				<div class="flex items-center gap-2 sm:hidden">
					<ThemeToggle />

					<button
						type="button"
						onclick={() => (mobileOpen = !mobileOpen)}
						class="inline-flex size-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 transition-colors hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
						aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
						aria-expanded={mobileOpen}
					>
						<Icon name={mobileOpen ? 'x' : 'menu'} class="size-5" />
					</button>
				</div>
			</div>

			<!-- Mobile navigation -->
			{#if mobileOpen}
				<div class="border-t border-slate-200/70 py-4 dark:border-slate-800/70">
					<nav class="space-y-1" aria-label="Mobile navigation">
						{#each publicNavLinks as link (link.href)}
							<a
								href={resolve(link.href)}
								class="flex items-center justify-between rounded-xl px-3 py-3 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
							>
								{link.label}
								<Icon name="arrow-right" class="size-4 opacity-40" />
							</a>
						{/each}

						{#if authStore.isAuthenticated && !authStore.isStaff}
							<a
								href={resolve('/bookings')}
								class="flex items-center justify-between rounded-xl px-3 py-3 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
							>
								My bookings
								<Icon name="arrow-right" class="size-4 opacity-40" />
							</a>
						{/if}

						{#if authStore.isStaff}
							<a
								href={resolve('/app')}
								class="flex items-center justify-between rounded-xl px-3 py-3 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
							>
								Dashboard
								<Icon name="arrow-right" class="size-4 opacity-40" />
							</a>
						{/if}
					</nav>

					<div class="mt-4 border-t border-slate-200/70 pt-4 dark:border-slate-800/70">
						{#if authStore.isAuthenticated}
							{#if authStore.isStaff}
								<div class="mb-3">
									<TenantSwitcher />
								</div>
							{/if}

							<Button
								variant="outline"
								size="sm"
								class="w-full"
								onclick={handleSignOut}
							>
								Sign out
							</Button>
						{:else}
							<div class="grid grid-cols-2 gap-2">
								<Button
									variant="outline"
									size="sm"
									href={resolve('/login')}
								>
									Sign in
								</Button>

								<Button
									size="sm"
									href={resolve('/register')}
								>
									Get started
								</Button>
							</div>
						{/if}
					</div>
				</div>
			{/if}
		</div>
	</header>
{:else}
	<!-- Compact application/demo shell -->
	<header
		class="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950"
	>
		<div class="mx-auto flex min-h-14 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
			<div class="flex min-w-0 items-center gap-5">
				<a
					href={resolve('/')}
					class="shrink-0 transition-opacity hover:opacity-80"
					aria-label="NOVA home"
				>
					<Logo />
				</a>

				<div class="hidden h-5 w-px bg-slate-200 sm:block dark:bg-slate-800"></div>

				<a
					href={resolve('/discover')}
					class="hidden text-sm font-medium text-slate-600 transition-colors hover:text-slate-950 sm:block dark:text-slate-300 dark:hover:text-white"
				>
					Find a salon
				</a>

				{#if authStore.isAuthenticated && !authStore.isStaff}
					<a
						href={resolve('/bookings')}
						class="hidden text-sm font-medium text-slate-600 transition-colors hover:text-slate-950 sm:block dark:text-slate-300 dark:hover:text-white"
					>
						My bookings
					</a>
				{/if}

				{#if authStore.isStaff}
					<a
						href={resolve('/app')}
						class="hidden text-sm font-semibold text-slate-700 transition-colors hover:text-slate-950 sm:block dark:text-slate-200 dark:hover:text-white"
					>
						Dashboard
					</a>
				{/if}
			</div>

			<div class="flex shrink-0 items-center gap-2">
				<ThemeToggle />

				<div class="hidden h-6 w-px bg-slate-200 sm:block dark:bg-slate-800"></div>

				{#if authStore.isAuthenticated}
					{#if authStore.isStaff}
						<div class="hidden w-44 sm:block">
							<TenantSwitcher />
						</div>
					{/if}

					<Button
						variant="ghost"
						size="sm"
						onclick={handleSignOut}
					>
						<span class="hidden sm:inline">Sign out</span>
						<Icon name="log-out" class="size-4 sm:hidden" />
					</Button>
				{:else}
					<Button
						variant="ghost"
						size="sm"
						href={resolve('/login')}
					>
						Sign in
					</Button>

					<Button
						size="sm"
						href={resolve('/register')}
						class="hidden sm:inline-flex"
					>
						Sign up
					</Button>
				{/if}
			</div>
		</div>
	</header>
{/if}
