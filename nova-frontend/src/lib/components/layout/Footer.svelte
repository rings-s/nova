<script>
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import Logo from './Logo.svelte';

	const year = new Date().getFullYear();
</script>

<footer class="border-t border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950">
	<div class="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 lg:px-8">
		<div class="grid grid-cols-2 gap-8 lg:grid-cols-4">
			<div>
				<h3 class="text-sm font-semibold text-slate-900 dark:text-slate-100">Product</h3>
				<ul class="mt-4 space-y-3 text-sm">
					<li>
						<a
							href={resolve('/features')}
							class="text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
							>Features</a
						>
					</li>
					<li>
						<a
							href={resolve('/pricing')}
							class="text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
							>Pricing</a
						>
					</li>
					<li>
						<a
							href={resolve('/discover')}
							class="text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
							>Find a salon</a
						>
					</li>
				</ul>
			</div>

			<div>
				<h3 class="text-sm font-semibold text-slate-900 dark:text-slate-100">Company</h3>
				<ul class="mt-4 space-y-3 text-sm">
					<li>
						<a
							href={resolve('/about')}
							class="text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
							>About</a
						>
					</li>
				</ul>
			</div>

			<div>
				<h3 class="text-sm font-semibold text-slate-900 dark:text-slate-100">Account</h3>
				<ul class="mt-4 space-y-3 text-sm">
					{#if authStore.isAuthenticated}
						{#if authStore.isStaff}
							<li>
								<a
									href={resolve('/app')}
									class="text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
									>Dashboard</a
								>
							</li>
						{:else}
							<li>
								<a
									href={resolve('/bookings')}
									class="text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
									>My bookings</a
								>
							</li>
						{/if}
					{:else}
						<li>
							<a
								href={resolve('/login')}
								class="text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
								>Sign in</a
							>
						</li>
						<li>
							<a
								href={resolve('/register')}
								class="text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
								>Sign up</a
							>
						</li>
					{/if}
				</ul>
			</div>
		</div>

		<div
			class="mt-12 flex flex-col items-start justify-between gap-4 border-t border-slate-200 pt-8 sm:flex-row sm:items-center dark:border-slate-800"
		>
			<Logo variant="mark" />
			<p class="text-sm text-slate-500 dark:text-slate-400">© {year} NOVA. All rights reserved.</p>
		</div>
	</div>
</footer>
