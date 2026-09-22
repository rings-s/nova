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

	import Icon from '$lib/components/ui/Icon.svelte';
	import Avatar from '$lib/components/ui/Avatar.svelte';
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
	<div class="mb-4">
		<Button variant="ghost" size="sm" class="-ms-3" href={resolve('/app/customers')}>
			<Icon name="chevron-left" class="size-4 rtl:rotate-180" />
			Customers
		</Button>
	</div>

	<div class="mb-8 flex flex-wrap items-center gap-4">
		<Avatar name={customer.full_name} size="lg" />
		<div class="min-w-0">
			<h1 class="text-2xl font-semibold tracking-tight text-fg">{customer.full_name}</h1>
			<p class="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-fg-muted">
				<span class="inline-flex items-center gap-1.5"
					><Icon name="phone" class="size-4" />{customer.phone}</span
				>
				{#if customer.email}<span>{customer.email}</span>{/if}
			</p>
		</div>
	</div>

	<div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
		<div class="flex flex-col gap-8 lg:col-span-2">
			<section>
				<h2 class="mb-3 text-base font-semibold tracking-tight text-fg">
					Bookings <span class="ms-1 text-sm font-normal text-fg-muted">{bookings.length}</span>
				</h2>
				{#if bookings.length === 0}
					<EmptyState title="No bookings yet">
						{#snippet icon()}<Icon name="calendar" class="size-6" />{/snippet}
					</EmptyState>
				{:else}
					<div class="flex flex-col gap-3">
						{#each bookings as booking (booking.id)}
							<BookingCard {booking} />
						{/each}
					</div>
				{/if}
			</section>

			<section>
				<h2 class="mb-3 text-base font-semibold tracking-tight text-fg">Delivery log</h2>
				{#if notifications.length === 0}
					<EmptyState title="No messages sent yet">
						{#snippet icon()}<Icon name="chat-bubble" class="size-6" />{/snippet}
					</EmptyState>
				{:else}
					<Card padding="none">
						<div class="px-5">
							{#each notifications as notification (notification.id)}
								<NotificationRow {notification} />
							{/each}
						</div>
					</Card>
				{/if}
			</section>
		</div>

		<aside class="flex flex-col gap-6">
			<Card padding="none">
				{#snippet header()}
					<h2 class="text-sm font-semibold text-fg">Consent</h2>
					<p class="mt-0.5 text-xs text-fg-muted">What this customer agreed to receive (PDPL).</p>
				{/snippet}
				<div class="flex flex-col gap-3 p-5">
					<Checkbox label="Marketing offers" bind:checked={marketingConsent} />
					<Checkbox label="WhatsApp messages" bind:checked={whatsappConsent} />
				</div>
				{#snippet footer()}
					<div class="flex justify-end">
						<Button size="sm" loading={savingConsent} onclick={saveConsent}>Save consent</Button>
					</div>
				{/snippet}
			</Card>
			{#if customer.notes}
				<Card padding="md">
					<h2 class="mb-2 text-sm font-semibold text-fg">Notes</h2>
					<p class="text-sm whitespace-pre-line text-fg-secondary">{customer.notes}</p>
				</Card>
			{/if}
		</aside>
	</div>
{/if}
