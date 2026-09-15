<script>
	import Input from '../ui/Input.svelte';
	import Button from '../ui/Button.svelte';
	import Alert from '../ui/Alert.svelte';
	import { authStore } from '../../stores/auth.svelte.js';

	/** @type {{ onsuccess?: () => void }} */
	let { onsuccess } = $props();

	let email = $state('');
	let password = $state('');
	let error = $state(/** @type {string|null} */ (null));
	let loading = $state(false);

	async function handleSubmit(event) {
		event.preventDefault();
		error = null;
		loading = true;
		try {
			await authStore.login({ email, password });
			onsuccess?.();
		} catch (err) {
			// The backend answers every login refusal — bad password, or a
			// locked account — with the same `invalid_credentials` message, on
			// purpose (CLAUDE.md, "Login"): it must not tell an attacker which.
			error = err?.message ?? 'Could not sign in.';
		} finally {
			loading = false;
		}
	}
</script>

<form class="flex flex-col gap-4" onsubmit={handleSubmit}>
	{#if error}
		<Alert tone="error">{error}</Alert>
	{/if}
	<Input type="email" label="Email" required autocomplete="email" bind:value={email} />
	<Input
		type="password"
		label="Password"
		required
		autocomplete="current-password"
		bind:value={password}
	/>
	<Button type="submit" {loading} fullWidth>Sign in</Button>
</form>
