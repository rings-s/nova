<script>
	import { i18n, t } from '$lib/i18n/index.svelte.js';
	// The form's own stylesheet, scoped by Moyasar to `div#mysr`. Safe to import
	// here: it is CSS, and the library itself is only loaded in the browser.
	import 'moyasar-payment-form/dist/moyasar.css';
	import { onMount } from 'svelte';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';

	/**
	 * Moyasar's Payment Form (docs.moyasar.com, "Basic Integration"), paying the
	 * invoice the API opened for this payment.
	 *
	 * Every option that matters comes from the server (`PaymentIntent.checkout`):
	 * the invoice id binds the form to that invoice, and Moyasar refuses a
	 * payment whose amount differs from it. Card details go from this form
	 * straight to Moyasar with the publishable key, never through NOVA.
	 *
	 * On submit Moyasar runs 3-D Secure as a full-page redirect, then sends the
	 * payer to `callback_url` with its own `id`, `status` and `message` added.
	 * That page asks the API to check the payment with Moyasar (`/sync`); nothing
	 * the redirect says is trusted.
	 *
	 * Apple Pay, Google Pay and Samsung Pay are left off: each loads a
	 * third-party script (blocked by the CSP in vite.config.js) and needs the
	 * domain registered with Moyasar first.
	 *
	 * @type {{ config: import('$lib/api/payment.js').PaymentFormConfig }}
	 */
	let { config } = $props();

	/** @type {HTMLDivElement | undefined} */
	let container = $state();
	let ready = $state(false);
	let failed = $state(false);

	onMount(() => {
		let disposed = false;
		(async () => {
			try {
				const { default: Moyasar } = await import('moyasar-payment-form');
				if (disposed || !container) return;
				Moyasar.init({
					element: container,
					publishable_api_key: config.publishable_api_key,
					invoice_id: config.invoice_id,
					amount: config.amount,
					currency: config.currency,
					description: config.description,
					callback_url: config.callback_url,
					language: i18n.locale,
					methods: ['creditcard', 'stcpay'],
					supported_networks: ['mada', 'visa', 'mastercard'],
					/** @param {unknown} error */
					on_failure: async (error) => {
						// Moyasar's own wording, in the form's language; nothing charged.
						toastStore.error(
							typeof error === 'string' && error
								? error
								: t("The payment didn't go through and nothing was charged.")
						);
					}
				});
				ready = true;
			} catch (err) {
				console.error(err);
				failed = true;
			}
		})();
		return () => {
			disposed = true;
		};
	});
</script>

{#if failed}
	<Alert tone="error">
		{t("The payment form couldn't load. Check your connection and try again.")}
	</Alert>
{:else}
	<div class="space-y-3">
		{#if !ready}
			<div class="space-y-3" aria-hidden="true">
				<Skeleton class="h-10 w-full rounded-control" />
				<Skeleton class="h-10 w-full rounded-control" />
				<Skeleton class="h-11 w-full rounded-control" />
			</div>
		{/if}
		<!-- Moyasar renders into this; it follows the page's `dir` for Arabic. -->
		<div bind:this={container} class="moyasar-form"></div>
		<p class="flex items-center justify-center gap-1.5 text-xs text-fg-muted">
			<Icon name="lock" class="size-3.5" />
			{t('Secured by Moyasar. Your card details never reach NOVA.')}
		</p>
	</div>
{/if}
