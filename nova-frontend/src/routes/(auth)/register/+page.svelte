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
	<title>Create Account — NOVA GCC Salon Operating System</title>
</svelte:head>

<div
	class="rounded-3xl border border-slate-200 bg-white p-7 shadow-xl sm:p-8 dark:border-slate-800 dark:bg-slate-900"
>
	<!-- Header -->
	<div class="flex items-center justify-between gap-4">
		<Logo />

		<Badge tone="success" size="sm">
			14-Day Free Trial
		</Badge>
	</div>

	<!-- Intro -->
	<div class="mt-8">
		<p class="text-xs font-bold uppercase tracking-[0.16em] text-brand-600 dark:text-brand-400">
			Get started
		</p>

		<h1 class="mt-2 text-display-md font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
			Create your NOVA account
		</h1>

		<p class="mt-2 max-w-sm text-sm leading-6 text-slate-600 dark:text-slate-400">
			Book appointments as a customer, or set up your salon on NOVA.
		</p>
	</div>

	<!-- Form -->
	<div class="mt-7">
		<RegisterForm onsuccess={handleSuccess} />
	</div>

	<!-- Login -->
	<div class="mt-7 border-t border-slate-100 pt-5 text-center dark:border-slate-800">
		<p class="text-xs text-slate-500 dark:text-slate-400">
			Already have an account?
			<a
				href={resolve('/login')}
				class="ml-1 font-bold text-brand-600 transition-colors hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300"
			>
				Sign in
			</a>
		</p>
	</div>
</div>
