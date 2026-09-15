<script>
	import Input from '../ui/Input.svelte';
	import Button from '../ui/Button.svelte';
	import Alert from '../ui/Alert.svelte';
	import { authStore } from '../../stores/auth.svelte.js';

	/** @type {{ onsuccess?: (user: import('../../api/auth.js').RegisteredUser) => void }} */
	let { onsuccess } = $props();

	let fullName = $state('');
	let email = $state('');
	let phone = $state('');
	let password = $state('');
	let error = $state(/** @type {string|null} */ (null));
	let loading = $state(false);

	async function handleSubmit(event) {
		event.preventDefault();
		error = null;
		loading = true;
		try {
			const user = await authStore.register({
				email,
				password,
				fullName,
				phone: phone || null
			});
			onsuccess?.(user);
		} catch (err) {
			error = err?.field ? `${err.field}: ${err.message}` : err?.message ?? 'Could not register.';
		} finally {
			loading = false;
		}
	}
</script>

<form class="flex flex-col gap-4" onsubmit={handleSubmit}>
	{#if error}
		<Alert tone="error">{error}</Alert>
	{/if}
	<Input label="Full name" required autocomplete="name" bind:value={fullName} />
	<Input type="email" label="Email" required autocomplete="email" bind:value={email} />
	<Input type="tel" label="Phone" hint="Optional — a GCC number." autocomplete="tel" bind:value={phone} />
	<Input
		type="password"
		label="Password"
		required
		hint="At least 12 characters."
		autocomplete="new-password"
		bind:value={password}
	/>
	<Button type="submit" {loading} fullWidth>Create account</Button>
</form>
