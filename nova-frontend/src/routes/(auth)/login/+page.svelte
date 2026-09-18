<script>
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import LoginForm from '$lib/components/auth/LoginForm.svelte';
	import Logo from '$lib/components/layout/Logo.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';

	$effect(() => {
		if (authStore.isAuthenticated) {
			goto(resolve('/'));
		}
	});

	function handleSuccess() {
		toastStore.success('Signed in successfully.');
		goto(resolve('/'));
	}
</script>

<svelte:head>
	<title>Sign In — NOVA GCC Salon Operating System</title>
</svelte:head>

<div
	class="rounded-3xl border border-slate-200 bg-white p-7 shadow-xl sm:p-8 dark:border-slate-800 dark:bg-slate-900"
>
	<!-- Header -->
	<div class="flex items-center justify-between gap-4">
		<Logo />

		<Badge tone="accent" size="sm">
			GCC Salon OS
		</Badge>
	</div>

	<!-- Intro -->
	<div class="mt-8">
		<p class="text-xs font-bold uppercase tracking-[0.16em] text-brand-600 dark:text-brand-400">
			Welcome back
		</p>

		<h1 class="mt-2 text-display-md font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
			Sign in to NOVA
		</h1>

		<p class="mt-2 max-w-sm text-sm leading-6 text-slate-600 dark:text-slate-400">
			Access your salon workspace, front desk, and personal appointments.
		</p>
	</div>

	<!-- Form -->
	<div class="mt-7">
		<LoginForm onsuccess={handleSuccess} />
	</div>

	<!-- Register -->
	<div class="mt-7 border-t border-slate-100 pt-5 text-center dark:border-slate-800">
		<p class="text-xs text-slate-500 dark:text-slate-400">
			New to NOVA?
			<a
				href={resolve('/register')}
				class="ml-1 font-bold text-brand-600 transition-colors hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300"
			>
				Create an account
			</a>
		</p>
	</div>
</div>
