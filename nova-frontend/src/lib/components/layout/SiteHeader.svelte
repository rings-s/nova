<script>
	import { t, m } from '$lib/i18n/index.svelte.js';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';

	import { authStore } from '../../stores/auth.svelte.js';
	import { toastStore } from '../../stores/toast.svelte.js';
	import { isPublicChromeRoute } from '../../utils/routeChrome.js';

	import Button from '../ui/Button.svelte';
	import Icon from '../ui/Icon.svelte';
	import ThemeToggle from '../ui/ThemeToggle.svelte';
	import LanguageSwitch from '../ui/LanguageSwitch.svelte';
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

	/** Escape closes the menu, as it would any disclosure. @param {KeyboardEvent} event */
	function onKeydown(event) {
		if (event.key === 'Escape' && mobileOpen) mobileOpen = false;
	}

	/** @type {{ href: '/about'|'/features'|'/pricing'|'/discover', label: string }[]} */
	const publicNavLinks = [
		{ href: '/about', label: m('About') },
		{ href: '/features', label: m('Features') },
		{ href: '/pricing', label: m('Pricing') },
		{ href: '/discover', label: m('Find a salon') }
	];

	async function handleSignOut() {
		authStore.logout();
		toastStore.info(t('Signed out.'));
		await goto(resolve('/'));
	}
</script>

<svelte:window onkeydown={onKeydown} />

{#if isDashboard}
	<!-- /app renders its own shell in routes/app/+layout.svelte -->
{:else if isPublic}
	<header class="sticky top-0 z-40 border-b border-line/70 bg-surface/85 backdrop-blur-xl">
		<div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
			<div class="flex min-h-16 items-center justify-between gap-6">
				<!-- Brand -->
				<div class="flex min-w-0 items-center gap-6 xl:gap-8">
					<a
						href={resolve('/')}
						class="shrink-0 transition-opacity hover:opacity-80"
						aria-label={t('NOVA home')}
					>
						<Logo />
					</a>

					<!-- Desktop navigation -->
					<nav class="hidden items-center gap-5 lg:flex xl:gap-7" aria-label={t('Main navigation')}>
						{#each publicNavLinks as link (link.href)}
							<a
								href={resolve(link.href)}
								class="relative py-5 text-sm font-medium text-fg-secondary transition-colors hover:text-fg"
							>
								{t(link.label)}
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
								{t('Dashboard')}
							</a>
						{:else}
							<a
								href={resolve('/bookings')}
								class="hidden text-sm font-semibold text-fg-secondary transition-colors hover:text-fg lg:block"
							>
								{t('My bookings')}
							</a>
							<a
								href={resolve('/business/new')}
								class="hidden text-sm font-semibold text-accent transition-colors hover:underline lg:block"
							>
								{t('List your business')}
							</a>
						{/if}
					{/if}
				</div>

				<!-- Desktop actions. The page links only fit from `lg`, so everything
				     below that uses the menu; one breakpoint for both, or a band of
				     widths shows neither. -->
				<div class="hidden shrink-0 items-center gap-2 lg:flex">
					<LanguageSwitch />
					<ThemeToggle />

					<div class="mx-1 h-6 w-px bg-line"></div>

					{#if authStore.isAuthenticated}
						{#if authStore.isStaff}
							<div class="w-36 xl:w-44">
								<TenantSwitcher />
							</div>
						{/if}

						<Button variant="ghost" size="sm" onclick={handleSignOut} class="text-fg-secondary">
							{t('Sign out')}
						</Button>
					{:else}
						<Button variant="ghost" size="sm" href={resolve('/login')}>{t('Sign in')}</Button>

						<Button size="sm" href={resolve('/register')}>{t('Get started')}</Button>
					{/if}
				</div>

				<!-- Phone and tablet controls -->
				<div class="flex shrink-0 items-center gap-2 lg:hidden">
					{#if !authStore.isAuthenticated}
						<!-- Room for them from `sm`; below that they are in the menu. The
						     wrapper hides them: `Button`'s own `inline-flex` would beat a
						     `hidden` passed to it. -->
						<div class="hidden items-center gap-2 sm:flex">
							<Button variant="ghost" size="sm" href={resolve('/login')}>{t('Sign in')}</Button>
							<Button size="sm" href={resolve('/register')}>{t('Get started')}</Button>
						</div>
					{/if}
					<LanguageSwitch compact />
					<ThemeToggle />

					<button
						type="button"
						aria-controls="site-mobile-menu"
						onclick={() => (mobileOpen = !mobileOpen)}
						class="inline-flex size-10 items-center justify-center rounded-control border border-line bg-surface text-fg-secondary transition-colors hover:bg-surface-muted"
						aria-label={mobileOpen ? t('Close menu') : t('Open menu')}
						aria-expanded={mobileOpen}
					>
						<Icon name={mobileOpen ? 'x' : 'menu'} class="size-5" />
					</button>
				</div>
			</div>

			<!-- Phone and tablet navigation -->
			{#if mobileOpen}
				<div
					id="site-mobile-menu"
					class="max-h-[calc(100dvh-4rem)] overflow-y-auto border-t border-line/70 py-4 lg:hidden"
				>
					<nav class="space-y-1" aria-label={t('Mobile navigation')}>
						{#each publicNavLinks as link (link.href)}
							<a
								href={resolve(link.href)}
								class="flex items-center justify-between rounded-card px-3 py-3 text-sm font-medium text-fg-secondary transition-colors hover:bg-surface-muted"
							>
								{t(link.label)}
								<Icon name="arrow-right" class="size-4 opacity-40 rtl:rotate-180" />
							</a>
						{/each}

						{#if authStore.isAuthenticated && !authStore.isStaff}
							<a
								href={resolve('/bookings')}
								class="flex items-center justify-between rounded-card px-3 py-3 text-sm font-medium text-fg-secondary hover:bg-surface-muted"
							>
								{t('My bookings')}
								<Icon name="arrow-right" class="size-4 opacity-40 rtl:rotate-180" />
							</a>
							<a
								href={resolve('/business/new')}
								class="flex items-center justify-between rounded-card px-3 py-3 text-sm font-medium text-accent hover:bg-surface-muted"
							>
								{t('List your business')}
								<Icon name="arrow-right" class="size-4 opacity-40 rtl:rotate-180" />
							</a>
						{/if}

						{#if authStore.isStaff}
							<a
								href={resolve('/app')}
								class="flex items-center justify-between rounded-card px-3 py-3 text-sm font-medium text-fg-secondary hover:bg-surface-muted"
							>
								{t('Dashboard')}
								<Icon name="arrow-right" class="size-4 opacity-40 rtl:rotate-180" />
							</a>
						{/if}
					</nav>

					<div
						class={[
							'mt-4 border-t border-line/70 pt-4',
							// Signed out, its only content is in the bar itself from `sm`.
							!authStore.isAuthenticated && 'sm:hidden'
						]}
					>
						{#if authStore.isAuthenticated}
							{#if authStore.isStaff}
								<div class="mb-3">
									<TenantSwitcher />
								</div>
							{/if}

							<Button variant="outline" size="sm" class="w-full" onclick={handleSignOut}>
								{t('Sign out')}
							</Button>
						{:else}
							<div class="grid grid-cols-2 gap-2">
								<Button variant="outline" size="sm" href={resolve('/login')}>{t('Sign in')}</Button>

								<Button size="sm" href={resolve('/register')}>{t('Get started')}</Button>
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
					aria-label={t('NOVA home')}
				>
					<Logo />
				</a>

				<div class="hidden h-5 w-px bg-line sm:block"></div>

				<a
					href={resolve('/discover')}
					class="hidden text-sm font-medium text-fg-secondary transition-colors hover:text-fg sm:block"
				>
					{t('Find a salon')}
				</a>

				{#if authStore.isAuthenticated && !authStore.isStaff}
					<a
						href={resolve('/bookings')}
						class="hidden text-sm font-medium text-fg-secondary transition-colors hover:text-fg sm:block"
					>
						{t('My bookings')}
					</a>
				{/if}

				{#if authStore.isStaff}
					<a
						href={resolve('/app')}
						class="hidden text-sm font-semibold text-fg-secondary transition-colors hover:text-fg sm:block"
					>
						{t('Dashboard')}
					</a>
				{/if}
			</div>

			<div class="flex shrink-0 items-center gap-2">
				<LanguageSwitch compact />
				<ThemeToggle />

				<div class="hidden h-6 w-px bg-line sm:block"></div>

				{#if authStore.isAuthenticated}
					{#if authStore.isStaff}
						<div class="hidden w-44 sm:block">
							<TenantSwitcher />
						</div>
					{/if}

					<Button variant="ghost" size="sm" onclick={handleSignOut}>
						<span class="hidden sm:inline">{t('Sign out')}</span>
						<Icon name="log-out" class="size-4 sm:hidden" />
					</Button>
				{:else}
					<Button variant="ghost" size="sm" href={resolve('/login')}>{t('Sign in')}</Button>

					<Button size="sm" href={resolve('/register')} class="hidden sm:inline-flex">
						{t('Sign up')}
					</Button>
				{/if}
			</div>
		</div>
	</header>
{/if}
