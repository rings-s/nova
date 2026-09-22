<script>
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { afterSignIn } from '$lib/utils/landing.js';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import LoginForm from '$lib/components/auth/LoginForm.svelte';
	import Logo from '$lib/components/layout/Logo.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';

	/** Staff to the dashboard, customers to the site — or back where they were. */
	function leave() {
		// `afterSignIn` only returns a same-site path (see `safeNext`).
		// eslint-disable-next-line svelte/no-navigation-without-resolve
		goto(afterSignIn(authStore, page.url.searchParams.get('next')), { replaceState: true });
	}

	// Already signed in when arriving here: nothing to do on this page.
	$effect(() => {
		if (authStore.isAuthenticated) leave();
	});

	function handleSuccess() {
		toastStore.success('Signed in successfully.');
		leave();
	}
</script>

<svelte:head>
	<title>Sign in — NOVA</title>
</svelte:head>

<div class="animate-scale-in rounded-panel border border-line bg-surface p-7 shadow-overlay sm:p-9">
	<!-- Header -->
	<div class="flex items-center justify-between gap-4">
		<Logo />

		<Badge tone="accent" size="sm">GCC Salon OS</Badge>
	</div>

	<!-- Intro -->
	<div class="mt-8">
		<p class="text-xs font-semibold tracking-wider text-accent uppercase">Welcome back</p>

		<h1 class="mt-2 text-display-md font-semibold tracking-tight text-fg">Sign in to NOVA</h1>

		<p class="mt-2 max-w-sm text-sm leading-6 text-fg-muted">
			Access your salon workspace, front desk, and personal appointments.
		</p>
	</div>

	<!-- Form -->
	<div class="mt-7">
		<LoginForm onsuccess={handleSuccess} />
	</div>

	<!-- Register -->
	<div class="mt-8 border-t border-line-subtle pt-6 text-center">
		<p class="text-sm text-fg-muted">
			New to NOVA?
			<a href={resolve('/register')} class="ms-1 font-semibold text-accent hover:underline">
				Create an account
			</a>
		</p>
	</div>
</div>
