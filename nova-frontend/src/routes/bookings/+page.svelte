<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * The customer's own bookings, aggregated across every tenant they've
	 * booked with on this browser (`customerTenantsStore` — see its own
	 * comment for why: there is no cross-tenant "my bookings" endpoint).
	 */
	import { goto, replaceState } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { syncPayment } from '$lib/api/payment.js';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { customerTenantsStore } from '$lib/stores/customerTenants.svelte.js';
	import { listBookings, cancelBooking } from '$lib/api/booking.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import BookingCard from '$lib/components/booking/BookingCard.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import StatCard from '$lib/components/ui/StatCard.svelte';
	import Tabs from '$lib/components/ui/Tabs.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import Container from '$lib/components/marketing/Container.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Textarea from '$lib/components/ui/Textarea.svelte';
	import StarInput from '$lib/components/review/StarInput.svelte';
	import RatingStars from '$lib/components/review/RatingStars.svelte';
	import { listMyReviews, submitReview } from '$lib/api/review.js';
	import { issueTicket } from '$lib/api/queue.js';
	import { savedTicket, saveTicket } from '$lib/stores/tickets.js';
	import TicketCard from '$lib/components/ticket/TicketCard.svelte';

	$effect(() => {
		if (!authStore.isAuthenticated) {
			// eslint-disable-next-line svelte/no-navigation-without-resolve
			goto(`${resolve('/login')}?next=${encodeURIComponent('/bookings')}`, { replaceState: true });
		}
	});

	/** @typedef {{ tenantId: string, businessName: string, booking: import('$lib/api/booking.js').Booking }} Row */
	let loading = $state(true);
	let rows = $state(/** @type {Row[]} */ ([]));
	let cancellingId = $state(/** @type {string|null} */ (null));
	let activeTab = $state('all'); // 'all' | 'upcoming' | 'completed' | 'cancelled'

	/** Booking id → the star rating the customer gave it. */
	let ratings = $state(/** @type {Record<string, number>} */ ({}));
	let rateTarget = $state(/** @type {Row | null} */ (null));
	let rateValue = $state(0);
	let rateComment = $state('');
	let rating = $state(false);

	/** The ticket being shown, with the row it belongs to. */
	let ticketFor = $state(
		/** @type {{ row: Row, ticket: import('$lib/stores/tickets.js').StoredTicket }|null} */ (null)
	);
	let ticketLoadingId = $state(/** @type {string|null} */ (null));

	/** Bookings a customer can still check in with. @param {Row} row */
	function hasTicket(row) {
		return ['draft', 'pending_payment', 'confirmed'].includes(row.booking.status);
	}

	/**
	 * The QR for a booking: the one this device already holds, else a new one.
	 * @param {Row} row
	 */
	async function showTicket(row) {
		const kept = savedTicket(row.booking.id);
		if (kept) {
			ticketFor = { row, ticket: kept };
			return;
		}
		ticketLoadingId = row.booking.id;
		try {
			const issued = await issueTicket(row.tenantId, { bookingId: row.booking.id });
			saveTicket(row.booking.id, issued);
			ticketFor = { row, ticket: issued };
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			ticketLoadingId = null;
		}
	}

	/** @param {Row} row */
	function openRate(row) {
		rateTarget = row;
		rateValue = 0;
		rateComment = '';
	}

	async function submitRating() {
		if (!rateTarget || rateValue < 1) return;
		rating = true;
		try {
			const review = await submitReview(rateTarget.tenantId, {
				bookingId: rateTarget.booking.id,
				rating: rateValue,
				comment: rateComment.trim() || null
			});
			ratings = { ...ratings, [review.booking_id]: review.rating };
			toastStore.success(
				t('Thanks — you rated {name} {rating}/5.', {
					name: rateTarget.businessName,
					rating: review.rating
				})
			);
			rateTarget = null;
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			rating = false;
		}
	}

	async function loadAll() {
		loading = true;
		try {
			const results = await Promise.all(
				customerTenantsStore.all.map(async (tenant) => {
					const result = await listBookings(tenant.tenantId, { limit: 50 });
					return result.items.map((booking) => ({
						tenantId: tenant.tenantId,
						businessName: tenant.businessName,
						booking
					}));
				})
			);
			// What has already been rated, so a finished visit shows its stars
			// instead of asking again. One call per salon the customer has used.
			const reviewed = await Promise.all(
				customerTenantsStore.all.map((tenant) => listMyReviews(tenant.tenantId).catch(() => []))
			);
			ratings = Object.fromEntries(
				reviewed.flat().map((review) => [review.booking_id, review.rating])
			);
			rows = results
				.flat()
				.sort(
					(a, b) =>
						new Date(b.booking.starts_at).getTime() - new Date(a.booking.starts_at).getTime()
				);
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (authStore.isAuthenticated) loadAll();
	});

	/**
	 * Back from Moyasar's checkout: `?tenant=…&payment=…`. The server checks
	 * Moyasar's own record of the payment before anything is confirmed, so
	 * this page only reports what it found, then reloads the list.
	 */
	let returning = $state(/** @type {'checking'|'paid'|'pending'|'failed'|null} */ (null));
	/** Which return was handled, so a re-run of the effect does not check it twice. */
	let handledPayment = '';

	$effect(() => {
		const tenantId = page.url.searchParams.get('tenant');
		const paymentId = page.url.searchParams.get('payment');
		if (!authStore.isAuthenticated || !tenantId || !paymentId) return;
		if (handledPayment === paymentId) return;
		handledPayment = paymentId;
		returning = 'checking';
		syncPayment(tenantId, paymentId)
			.then((payment) => {
				if (payment.status === 'captured') {
					returning = 'paid';
					toastStore.success(t('Payment received. Your booking is confirmed.'));
				} else if (payment.status === 'failed') {
					returning = 'failed';
				} else {
					returning = 'pending';
				}
				return loadAll();
			})
			.catch((err) => {
				returning = null;
				toastStore.fromError(err);
			})
			.finally(() => {
				// Cleaned only now: SvelteKit refuses `replaceState` before its
				// router has started, which it has by the time the check returns.
				// A refresh before then only checks again, which is harmless.
				const clean = new URL(page.url);
				clean.searchParams.delete('tenant');
				clean.searchParams.delete('payment');
				// eslint-disable-next-line svelte/no-navigation-without-resolve
				replaceState(clean.pathname + clean.search, {});
			});
	});

	/** @param {Row} row */
	async function handleCancel(row) {
		if (!confirm(t('Are you sure you want to cancel this booking?'))) return;
		cancellingId = row.booking.id;
		try {
			const updated = await cancelBooking(row.tenantId, row.booking.id);
			rows = rows.map((r) => (r.booking.id === updated.id ? { ...r, booking: updated } : r));
			toastStore.success(t('Booking cancelled.'));
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			cancellingId = null;
		}
	}

	let upcomingCount = $derived(
		rows.filter((r) => r.booking.status === 'confirmed' || r.booking.status === 'pending_payment')
			.length
	);
	let completedCount = $derived(rows.filter((r) => r.booking.status === 'completed').length);
	let cancelledCount = $derived(
		rows.filter((r) => r.booking.status === 'cancelled' || r.booking.status === 'no_show').length
	);

	let filteredRows = $derived(
		rows.filter((r) => {
			if (activeTab === 'upcoming') {
				return r.booking.status === 'confirmed' || r.booking.status === 'pending_payment';
			}
			if (activeTab === 'completed') {
				return r.booking.status === 'completed';
			}
			if (activeTab === 'cancelled') {
				return r.booking.status === 'cancelled' || r.booking.status === 'no_show';
			}
			return true;
		})
	);
</script>

<svelte:head>
	<title>{t('My bookings')} — NOVA</title>
</svelte:head>

<Container size="lg" class="py-10 sm:py-14">
	<PageHeader
		eyebrow={t('Your account')}
		title={t('My bookings')}
		subtitle={t("Every appointment you've made across NOVA salons and spas.")}
	>
		{#snippet actions()}
			<Button href={resolve('/discover')} variant="outline">
				<Icon name="search" class="size-4" />
				{t('Find a salon')}
			</Button>
		{/snippet}
	</PageHeader>

	{#if returning === 'checking'}
		<Alert tone="info" class="mb-6">{t('Checking your payment with Moyasar…')}</Alert>
	{:else if returning === 'pending'}
		<Alert tone="warning" class="mb-6" dismissible ondismiss={() => (returning = null)}>
			{t(
				"We haven't received your payment yet. If you completed it, it will show here within a minute; your booking is held until then."
			)}
		</Alert>
	{:else if returning === 'failed'}
		<Alert tone="error" class="mb-6" dismissible ondismiss={() => (returning = null)}>
			{t(
				"The payment didn't go through and nothing was charged. You can try again from the salon's page."
			)}
		</Alert>
	{/if}

	{#if loading}
		<div class="flex justify-center py-20"><Spinner size="lg" /></div>
	{:else if rows.length === 0}
		<EmptyState
			title={t('No bookings yet')}
			description={t('Find a salon on the marketplace and book your first visit.')}
		>
			{#snippet icon()}<Icon name="calendar" class="size-6" />{/snippet}
			{#snippet action()}
				<Button href={resolve('/discover')}>{t('Browse salons')}</Button>
			{/snippet}
		</EmptyState>
	{:else}
		<div class="mb-8 grid grid-cols-3 gap-3 sm:gap-4">
			<StatCard label={t('Upcoming')} icon="calendar" value={upcomingCount} />
			<StatCard label={t('Completed')} icon="check" value={completedCount} />
			<StatCard label={t('Cancelled')} icon="x" value={cancelledCount} />
		</div>

		<div class="mb-5 flex flex-wrap items-center justify-between gap-3">
			<Tabs
				tabs={[
					{ id: 'all', label: t('All'), count: rows.length },
					{ id: 'upcoming', label: t('Upcoming'), count: upcomingCount },
					{ id: 'completed', label: t('Completed'), count: completedCount },
					{ id: 'cancelled', label: t('Cancelled'), count: cancelledCount }
				]}
				bind:active={activeTab}
			/>
		</div>

		{#if filteredRows.length === 0}
			<EmptyState title={t('Nothing here')} description={t('No appointments match this filter.')} />
		{:else}
			<div class="flex flex-col gap-3">
				{#each filteredRows as row (row.booking.id)}
					<BookingCard booking={row.booking} title={row.businessName}>
						{#snippet actions()}
							{#if row.booking.status === 'completed'}
								{#if ratings[row.booking.id]}
									<span class="inline-flex items-center gap-2 text-xs text-fg-muted">
										{t('You rated')}
										<RatingStars
											average={ratings[row.booking.id]}
											count={1}
											size="sm"
											showCount={false}
										/>
									</span>
								{:else}
									<Button size="sm" onclick={() => openRate(row)}>
										<Icon name="star" class="size-4" />
										{t('Rate visit')}
									</Button>
								{/if}
							{/if}
							{#if hasTicket(row)}
								<Button
									size="sm"
									loading={ticketLoadingId === row.booking.id}
									onclick={() => showTicket(row)}
								>
									<Icon name="shield-check" class="size-4" />
									{t('Show ticket')}
								</Button>
							{/if}
							{#if row.booking.status === 'confirmed' || row.booking.status === 'pending_payment'}
								<Button
									size="sm"
									variant="danger-ghost"
									loading={cancellingId === row.booking.id}
									onclick={() => handleCancel(row)}
								>
									{t('Cancel')}
								</Button>
							{/if}
							<Button size="sm" variant="outline" href={resolve('/discover')}
								>{t('Book again')}</Button
							>
						{/snippet}
					</BookingCard>
				{/each}
			</div>
			<Alert tone="info" class="mt-6">
				{t('Need to change a time or get directions? Reply to your WhatsApp confirmation message.')}
			</Alert>
		{/if}
	{/if}
</Container>

<Modal
	open={rateTarget !== null}
	title={t('Rate your visit')}
	description={rateTarget?.businessName ?? null}
	size="sm"
	onclose={() => (rateTarget = null)}
>
	<form
		id="rate-form"
		class="flex flex-col gap-5"
		onsubmit={(event) => {
			event.preventDefault();
			submitRating();
		}}
	>
		<StarInput bind:value={rateValue} label={t('How was it?')} />
		<Textarea
			label={t('Anything to add?')}
			hint={t(
				"Optional. Only the salon's staff see your comment; your stars count toward its public rating."
			)}
			rows={3}
			maxlength={1000}
			bind:value={rateComment}
		/>
	</form>
	{#snippet footer()}
		<Button variant="ghost" onclick={() => (rateTarget = null)}>{t('Cancel')}</Button>
		<Button type="submit" form="rate-form" loading={rating} disabled={rateValue < 1}>
			{t('Submit rating')}
		</Button>
	{/snippet}
</Modal>

<Modal open={ticketFor !== null} onclose={() => (ticketFor = null)} title={t('Your ticket')}>
	{#if ticketFor}
		<TicketCard
			class="border-0 shadow-none"
			qrPayload={ticketFor.ticket.qr_payload}
			ticketCode={ticketFor.ticket.ticket_code}
			startsAt={ticketFor.row.booking.starts_at}
			expiresAt={ticketFor.ticket.expires_at}
			businessName={ticketFor.row.businessName}
			status={ticketFor.row.booking.status}
		/>
	{/if}
</Modal>
