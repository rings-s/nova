<script>
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import RegisterForm from '$lib/components/auth/RegisterForm.svelte';
	import Logo from '$lib/components/layout/Logo.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';

	$effect(() => {
		if (authStore.isAuthenticated) {
			goto(resolve('/'));
		}
	});

	/**
	 * @param {import('$lib/api/auth.js').RegisteredUser} user
	 * @param {{ intent: 'customer'|'business_owner', tenant?: import('$lib/api/identity.js').Tenant }} details
	 */
	function handleSuccess(user, details) {
		if (details.intent === 'business_owner') {
			toastStore.success(`${details.tenant?.name_en || 'Your salon'} is on NOVA.`);
			goto(resolve('/app'));
		} else {
			toastStore.success('Account created successfully.');
			goto(resolve('/'));
		}
	}
</script>

<svelte:head>
	<title>Create account — NOVA</title>
</svelte:head>

<div class="animate-scale-in rounded-panel border border-line bg-surface p-7 shadow-overlay sm:p-9">
	<!-- Header -->
	<div class="flex items-center justify-between gap-4">
		<Logo />

		<Badge tone="success" size="sm">14-Day Free Trial</Badge>
	</div>

	<!-- Intro -->
	<div class="mt-8">
		<p class="text-xs font-semibold tracking-wider text-accent uppercase">Get started</p>

		<h1 class="mt-2 text-display-md font-semibold tracking-tight text-fg">
			Create your NOVA account
		</h1>

		<p class="mt-2 max-w-sm text-sm leading-6 text-fg-muted">
			Book appointments as a customer, or set up your salon on NOVA.
		</p>
	</div>

	<!-- Form -->
	<div class="mt-7">
		<RegisterForm onsuccess={handleSuccess} />
	</div>

	<!-- Login -->
	<div class="mt-8 border-t border-line-subtle pt-6 text-center">
		<p class="text-sm text-fg-muted">
			Already have an account?
			<a href={resolve('/login')} class="ms-1 font-semibold text-accent hover:underline">
				Sign in
			</a>
		</p>
	</div>
</div>
