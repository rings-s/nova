<script>
	/**
	 * One customer's record: profile, consent (PDPL — withdrawing must be as
	 * easy as giving it), their booking history at this business, and the
	 * delivery log for what they were actually told.
	 */
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { errorMessage } from '$lib/utils/errors.js';
	import { getCustomer, updateCustomerConsent } from '$lib/api/identity.js';
	import { listBookings } from '$lib/api/booking.js';
	import { listCustomerNotifications } from '$lib/api/notification.js';

	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Checkbox from '$lib/components/ui/Checkbox.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import BookingCard from '$lib/components/booking/BookingCard.svelte';
	import NotificationRow from '$lib/components/notification/NotificationRow.svelte';

	let tenantId = $derived(/** @type {string} */ (tenantStore.activeTenantId));
	let customerId = $derived(/** @type {string} */ (page.params.id));

	let loading = $state(true);
	let loadErrorMessage = $state(/** @type {string|null} */ (null));
	let customer = $state(/** @type {import('$lib/api/identity.js').Customer|null} */ (null));

	let bookings = $state(/** @type {import('$lib/api/booking.js').Booking[]} */ ([]));
	let notifications = $state(/** @type {import('$lib/api/notification.js').Notification[]} */ ([]));

	let savingConsent = $state(false);
	let marketingConsent = $state(false);
	let whatsappConsent = $state(false);

	async function load() {
		loading = true;
		loadErrorMessage = null;
		try {
			const [customerResult, bookingsResult, notificationsResult] = await Promise.all([
				getCustomer(tenantId, customerId),
				listBookings(tenantId, { customerId, limit: 20 }),
				listCustomerNotifications(tenantId, customerId, { limit: 20 })
			]);
			customer = customerResult;
			marketingConsent = customerResult.marketing_consent;
			whatsappConsent = customerResult.whatsapp_consent;
			bookings = bookingsResult.items;
			notifications = notificationsResult.items;
		} catch (err) {
			loadErrorMessage = errorMessage(err);
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		load();
	});

	async function saveConsent() {
		savingConsent = true;
		try {
			customer = await updateCustomerConsent(tenantId, customerId, {
				marketingConsent,
				whatsappConsent
			});
			toastStore.success('Consent updated.');
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			savingConsent = false;
		}
	}
</script>

<svelte:head><title>{customer?.full_name ?? 'Customer'} — NOVA</title></svelte:head>

{#if loading}
	<div class="flex justify-center py-12"><Spinner /></div>
{:else if loadErrorMessage}
	<Alert tone="error">{loadErrorMessage}</Alert>
{:else if customer}
	<PageHeader title={customer.full_name} subtitle={customer.phone} />

	<div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
		<div class="flex flex-col gap-6 lg:col-span-2">
			<section>
				<h2 class="mb-3 font-medium text-slate-900 dark:text-slate-100">Bookings</h2>
				{#if bookings.length === 0}
					<EmptyState title="No bookings yet" />
				{:else}
					<div class="flex flex-col gap-2">
						{#each bookings as booking (booking.id)}
							<BookingCard {booking} />
						{/each}
					</div>
				{/if}
			</section>

			<section>
				<h2 class="mb-3 font-medium text-slate-900 dark:text-slate-100">Delivery log</h2>
				{#if notifications.length === 0}
					<EmptyState title="No messages sent yet" />
				{:else}
					<Card padding="sm">
						{#each notifications as notification (notification.id)}
							<NotificationRow {notification} />
						{/each}
					</Card>
				{/if}
			</section>
		</div>

		<div>
			<Card padding="md">
				<h2 class="mb-3 font-medium text-slate-900 dark:text-slate-100">Consent</h2>
				<div class="flex flex-col gap-3">
					<Checkbox label="Marketing offers" bind:checked={marketingConsent} />
					<Checkbox label="WhatsApp messages" bind:checked={whatsappConsent} />
				</div>
				<Button class="mt-4" size="sm" loading={savingConsent} onclick={saveConsent}>Save</Button>
				{#if customer.notes}
					<p
						class="mt-4 border-t border-slate-100 pt-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400"
					>
						{customer.notes}
					</p>
				{/if}
			</Card>
		</div>
	</div>

	<div class="mt-6">
		<Button variant="ghost" size="sm" href={resolve('/app/customers')}>← Back to customers</Button>
	</div>
{/if}
