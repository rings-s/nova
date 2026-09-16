<script>
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import Card from '$lib/components/ui/Card.svelte';
	import LoginForm from '$lib/components/auth/LoginForm.svelte';

	$effect(() => {
		if (authStore.isAuthenticated) goto(resolve('/'));
	});

	function handleSuccess() {
		toastStore.success('Signed in.');
		goto(resolve('/'));
	}
</script>

<svelte:head><title>Sign in — NOVA</title></svelte:head>

<Card padding="lg">
	<h1 class="text-xl font-semibold text-slate-900 dark:text-slate-100">Welcome back</h1>
	<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">Sign in to manage your bookings.</p>

	<div class="mt-6">
		<LoginForm onsuccess={handleSuccess} />
	</div>

	<p class="mt-6 text-center text-sm text-slate-500 dark:text-slate-400">
		New to NOVA? <a
			href={resolve('/register')}
			class="font-medium text-brand-600 hover:text-brand-700 dark:text-brand-400"
			>Create an account</a
		>
	</p>
</Card>
