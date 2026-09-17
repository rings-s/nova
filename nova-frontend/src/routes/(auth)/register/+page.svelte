<script>
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import Card from '$lib/components/ui/Card.svelte';
	import RegisterForm from '$lib/components/auth/RegisterForm.svelte';
	import Logo from '$lib/components/layout/Logo.svelte';

	$effect(() => {
		if (authStore.isAuthenticated) goto(resolve('/'));
	});

	/**
	 * @param {import('$lib/api/auth.js').RegisteredUser} user
	 * @param {{ intent: 'customer'|'business_owner', tenant?: import('$lib/api/identity.js').Tenant }} details
	 */
	function handleSuccess(user, details) {
		if (details.intent === 'business_owner') {
			toastStore.success(`${details.tenant?.name_en} is on NOVA.`);
			goto(resolve('/app'));
		} else {
			toastStore.success('Account created.');
			goto(resolve('/'));
		}
	}
</script>

<svelte:head><title>Create an account — NOVA</title></svelte:head>

<Card padding="lg">
	<Logo class="mb-6" />
	<h1 class="text-xl font-semibold text-slate-900 dark:text-slate-100">Create your account</h1>
	<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">
		Book with any salon on NOVA, or list your own.
	</p>

	<div class="mt-6">
		<RegisterForm onsuccess={handleSuccess} />
	</div>

	<p class="mt-6 text-center text-sm text-slate-500 dark:text-slate-400">
		Already have an account? <a
			href={resolve('/login')}
			class="font-medium text-brand-600 hover:text-brand-700 dark:text-brand-400">Sign in</a
		>
	</p>
</Card>
