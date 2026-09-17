<script>
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import LoginForm from '$lib/components/auth/LoginForm.svelte';
	import Logo from '$lib/components/layout/Logo.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';

	$effect(() => {
		if (authStore.isAuthenticated) goto(resolve('/'));
	});

	function handleSuccess() {
		toastStore.success('Signed in successfully.');
		goto(resolve('/'));
	}
</script>

<svelte:head>
	<title>Sign In — NOVA GCC Salon Operating System</title>
</svelte:head>

<div class="rounded-3xl border border-slate-200 bg-white p-8 shadow-xl dark:border-slate-800 dark:bg-slate-900">
	<div class="flex items-center justify-between">
		<Logo />
		<Badge tone="brand" size="sm">GCC Salon OS</Badge>
	</div>

	<div class="mt-6">
		<h1 class="text-display-md font-bold tracking-tight text-slate-900 dark:text-slate-100">
			Welcome back
		</h1>
		<p class="mt-1.5 text-xs text-slate-600 dark:text-slate-400">
			Sign in to access your salon front-desk or personal appointments.
		</p>
	</div>

	<div class="mt-6">
		<LoginForm onsuccess={handleSuccess} />
	</div>

	<div class="mt-6 border-t border-slate-100 pt-5 dark:border-slate-800 text-center">
		<p class="text-xs text-slate-500 dark:text-slate-400">
			New to NOVA?{' '}
			<a
				href={resolve('/register')}
				class="font-bold text-brand-600 hover:text-brand-700 dark:text-brand-400"
			>
				Create an account
			</a>
		</p>
	</div>
</div>
