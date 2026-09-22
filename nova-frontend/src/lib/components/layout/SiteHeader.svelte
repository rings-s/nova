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
	// The dashboard draws its own chrome (sidebar + mobile top bar).
	let isDashboard = $derived(page.url.pathname.startsWith('/app'));
	let mobileOpen = $state(false);

	$effect(() => {
		page.url.pathname;
		mobileOpen = false;
	});

	/** @type {{ href: '/about'|'/features'|'/pricing'|'/discover', label: string }[]} */
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

{#if isDashboard}
	<!-- /app renders its own shell in routes/app/+layout.svelte -->
{:else if isPublic}
	<header class="sticky top-0 z-40 border-b border-line/70 bg-surface/85 backdrop-blur-xl">
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
								class="relative py-5 text-sm font-medium text-fg-secondary transition-colors hover:text-fg"
							>
								{link.label}
							</a>
						{/each}
					</nav>

					<!-- Authenticated shortcuts -->
					{#if authStore.isAuthenticated}
						<div class="hidden h-5 w-px bg-line lg:block"></div>

						{#if authStore.isStaff}
							<a
								href={resolve('/app')}
								class="hidden text-sm font-semibold text-fg-secondary transition-colors hover:text-fg lg:block"
							>
								Dashboard
							</a>
						{:else}
							<a
								href={resolve('/bookings')}
								class="hidden text-sm font-semibold text-fg-secondary transition-colors hover:text-fg lg:block"
							>
								My bookings
							</a>
						{/if}
					{/if}
				</div>

				<!-- Desktop actions -->
				<div class="hidden items-center gap-2 sm:flex">
					<ThemeToggle />

					<div class="mx-1 h-6 w-px bg-line"></div>

					{#if authStore.isAuthenticated}
						{#if authStore.isStaff}
							<div class="w-44">
								<TenantSwitcher />
							</div>
						{/if}

						<Button variant="ghost" size="sm" onclick={handleSignOut} class="text-fg-secondary">
							Sign out
						</Button>
					{:else}
						<Button variant="ghost" size="sm" href={resolve('/login')}>Sign in</Button>

						<Button size="sm" href={resolve('/register')}>Get started</Button>
					{/if}
				</div>

				<!-- Mobile controls -->
				<div class="flex items-center gap-2 sm:hidden">
					<ThemeToggle />

					<button
						type="button"
						onclick={() => (mobileOpen = !mobileOpen)}
						class="inline-flex size-10 items-center justify-center rounded-control border border-line bg-surface text-fg-secondary transition-colors hover:bg-surface-muted"
						aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
						aria-expanded={mobileOpen}
					>
						<Icon name={mobileOpen ? 'x' : 'menu'} class="size-5" />
					</button>
				</div>
			</div>

			<!-- Mobile navigation -->
			{#if mobileOpen}
				<div class="border-t border-line/70 py-4">
					<nav class="space-y-1" aria-label="Mobile navigation">
						{#each publicNavLinks as link (link.href)}
							<a
								href={resolve(link.href)}
								class="flex items-center justify-between rounded-card px-3 py-3 text-sm font-medium text-fg-secondary transition-colors hover:bg-surface-muted"
							>
								{link.label}
								<Icon name="arrow-right" class="size-4 opacity-40" />
							</a>
						{/each}

						{#if authStore.isAuthenticated && !authStore.isStaff}
							<a
								href={resolve('/bookings')}
								class="flex items-center justify-between rounded-card px-3 py-3 text-sm font-medium text-fg-secondary hover:bg-surface-muted"
							>
								My bookings
								<Icon name="arrow-right" class="size-4 opacity-40" />
							</a>
						{/if}

						{#if authStore.isStaff}
							<a
								href={resolve('/app')}
								class="flex items-center justify-between rounded-card px-3 py-3 text-sm font-medium text-fg-secondary hover:bg-surface-muted"
							>
								Dashboard
								<Icon name="arrow-right" class="size-4 opacity-40" />
							</a>
						{/if}
					</nav>

					<div class="mt-4 border-t border-line/70 pt-4">
						{#if authStore.isAuthenticated}
							{#if authStore.isStaff}
								<div class="mb-3">
									<TenantSwitcher />
								</div>
							{/if}

							<Button variant="outline" size="sm" class="w-full" onclick={handleSignOut}>
								Sign out
							</Button>
						{:else}
							<div class="grid grid-cols-2 gap-2">
								<Button variant="outline" size="sm" href={resolve('/login')}>Sign in</Button>

								<Button size="sm" href={resolve('/register')}>Get started</Button>
							</div>
						{/if}
					</div>
				</div>
			{/if}
		</div>
	</header>
{:else}
	<!-- Compact application/demo shell -->
	<header class="border-b border-line bg-surface">
		<div
			class="mx-auto flex min-h-14 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8"
		>
			<div class="flex min-w-0 items-center gap-5">
				<a
					href={resolve('/')}
					class="shrink-0 transition-opacity hover:opacity-80"
					aria-label="NOVA home"
				>
					<Logo />
				</a>

				<div class="hidden h-5 w-px bg-line sm:block"></div>

				<a
					href={resolve('/discover')}
					class="hidden text-sm font-medium text-fg-secondary transition-colors hover:text-fg sm:block"
				>
					Find a salon
				</a>

				{#if authStore.isAuthenticated && !authStore.isStaff}
					<a
						href={resolve('/bookings')}
						class="hidden text-sm font-medium text-fg-secondary transition-colors hover:text-fg sm:block"
					>
						My bookings
					</a>
				{/if}

				{#if authStore.isStaff}
					<a
						href={resolve('/app')}
						class="hidden text-sm font-semibold text-fg-secondary transition-colors hover:text-fg sm:block"
					>
						Dashboard
					</a>
				{/if}
			</div>

			<div class="flex shrink-0 items-center gap-2">
				<ThemeToggle />

				<div class="hidden h-6 w-px bg-line sm:block"></div>

				{#if authStore.isAuthenticated}
					{#if authStore.isStaff}
						<div class="hidden w-44 sm:block">
							<TenantSwitcher />
						</div>
					{/if}

					<Button variant="ghost" size="sm" onclick={handleSignOut}>
						<span class="hidden sm:inline">Sign out</span>
						<Icon name="log-out" class="size-4 sm:hidden" />
					</Button>
				{:else}
					<Button variant="ghost" size="sm" href={resolve('/login')}>Sign in</Button>

					<Button size="sm" href={resolve('/register')} class="hidden sm:inline-flex">
						Sign up
					</Button>
				{/if}
			</div>
		</div>
	</header>
{/if}
