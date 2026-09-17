<script>
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import RegisterForm from '$lib/components/auth/RegisterForm.svelte';
	import Logo from '$lib/components/layout/Logo.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';

	$effect(() => {
		if (authStore.isAuthenticated) goto(resolve('/'));
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

<div class="rounded-3xl border border-slate-200 bg-white p-8 shadow-xl dark:border-slate-800 dark:bg-slate-900">
	<div class="flex items-center justify-between">
		<Logo />
		<Badge tone="success" size="sm">14-Day Free Trial</Badge>
	</div>

	<div class="mt-6">
		<h1 class="text-display-md font-bold tracking-tight text-slate-900 dark:text-slate-100">
			Create your account
		</h1>
		<p class="mt-1.5 text-xs text-slate-600 dark:text-slate-400">
			Run your salon with 0% direct commission, or book with top salons.
		</p>
	</div>

	<div class="mt-6">
		<RegisterForm onsuccess={handleSuccess} />
	</div>

	<div class="mt-6 border-t border-slate-100 pt-5 dark:border-slate-800 text-center">
		<p class="text-xs text-slate-500 dark:text-slate-400">
			Already have an account?{' '}
			<a
				href={resolve('/login')}
				class="font-bold text-brand-600 hover:text-brand-700 dark:text-brand-400"
			>
				Sign in
			</a>
		</p>
	</div>
</div>
