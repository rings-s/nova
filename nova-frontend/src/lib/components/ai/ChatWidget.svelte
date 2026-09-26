<script>
	import { t, i18n } from '$lib/i18n/index.svelte.js';
	import { tick, onDestroy } from 'svelte';
	import { resolve } from '$app/paths';
	/**
	 * One conversation with a NOVA agent (docs/13), used by the staff AI
	 * workspace (/app/ai) and the storefront assistant.
	 *
	 * - A tool's write (a held slot, a queue place, a booking) is already
	 *   committed when a reply comes back, even if `requires_human_handoff` is
	 *   true, so they are shown regardless.
	 * - A held slot is an offer. The agent books it only after the customer
	 *   says yes in a later message (enforced by the backend), so the card's
	 *   button just sends that yes. The booking comes back as a QR ticket.
	 * - No agent cancels: a `pending_cancellations` entry still needs the
	 *   customer to confirm from their bookings.
	 * - Charts and proposed actions are the tools' output, never the model's
	 *   text, so they are rendered as-is.
	 * - Local models are slow (a turn can take a minute on a laptop), so the
	 *   pending state counts the seconds rather than spinning silently.
	 *
	 * Wrap it in `{#key}` to start a new conversation: the session id is made
	 * once per mount.
	 */
	import { sendChatMessage } from '../../api/ai.js';
	import { formatDateTime, formatRelative } from '../../utils/datetime.js';
	import { errorMessage } from '../../utils/errors.js';
	import Button from '../ui/Button.svelte';
	import Badge from '../ui/Badge.svelte';
	import Alert from '../ui/Alert.svelte';
	import Icon from '../ui/Icon.svelte';
	import ChartPanel from '../analytics/ChartPanel.svelte';
	import TicketCard from '../ticket/TicketCard.svelte';
	import { saveTicket } from '../../stores/tickets.js';
	import { customerTenantsStore } from '../../stores/customerTenants.svelte.js';

	/**
	 * @type {{
	 *   tenantId?: string|null,
	 *   agent?: string,
	 *   businessId?: string|null,
	 *   customerId?: string|null,
	 *   title?: string|null,
	 *   subtitle?: string|null,
	 *   starters?: string[],
	 *   referralToken?: string|null,
	 *   send?: ((params: { sessionId: string, message: string, locale: string, confirmHoldToken: string|null }) => Promise<import('../../api/ai.js').AiChatResponse>)|null,
	 *   intro?: string|null,
	 *   class?: string
	 * }}
	 */
	let {
		tenantId = null,
		agent = 'concierge_agent',
		businessId = null,
		customerId = null,
		title = null,
		subtitle = null,
		starters = [],
		referralToken = null,
		send = null,
		intro = null,
		class: className = 'h-[32rem]'
	} = $props();

	const sessionId = crypto.randomUUID();

	/**
	 * @typedef {{ role: 'user'|'assistant', text: string, response?: import('../../api/ai.js').AiChatResponse }} ChatMessage
	 */
	let messages = $state(/** @type {ChatMessage[]} */ ([]));
	let draft = $state('');
	let sending = $state(false);
	let error = $state(/** @type {string|null} */ (null));
	let elapsed = $state(0);

	/** @type {HTMLDivElement|undefined} */
	let scroller = $state();
	/** @type {ReturnType<typeof setInterval>|undefined} */
	let timer;
	onDestroy(() => clearInterval(timer));

	async function scrollToEnd() {
		await tick();
		scroller?.scrollTo({ top: scroller.scrollHeight, behavior: 'smooth' });
	}

	/**
	 * @param {string} text
	 * @param {string|null} [confirmHoldToken] the held slot whose "Yes, book it" was pressed:
	 *   the only confirmation the agent books on.
	 */
	async function ask(text, confirmHoldToken = null) {
		text = text.trim();
		if (!text || sending) return;

		messages = [...messages, { role: 'user', text }];
		draft = '';
		sending = true;
		error = null;
		elapsed = 0;
		timer = setInterval(() => (elapsed += 1), 1000);
		scrollToEnd();

		try {
			// The agent answers in the language the page is in.
			const response = send
				? await send({ sessionId, message: text, locale: i18n.locale, confirmHoldToken })
				: await sendChatMessage(tenantId ?? '', {
						sessionId,
						message: text,
						locale: i18n.locale,
						businessId,
						customerId,
						agent,
						referralToken,
						confirmHoldToken
					});
			messages = [...messages, { role: 'assistant', text: response.reply, response }];
			// Kept on this device, so My bookings shows this same QR rather than
			// reissuing (which would revoke the one just shown).
			// And the business is remembered, so the booking shows in My bookings,
			// which lists the businesses this device has booked with.
			for (const ticket of response.tickets ?? []) {
				saveTicket(ticket.booking_id, ticket);
				customerTenantsStore.add(ticket.tenant_id, ticket.business_name);
			}
		} catch (err) {
			error = errorMessage(err);
		} finally {
			clearInterval(timer);
			sending = false;
			scrollToEnd();
		}
	}

	/** @param {SubmitEvent} event */
	function submit(event) {
		event.preventDefault();
		ask(draft);
	}

	/** Enter sends; Shift+Enter is a new line. @param {KeyboardEvent} event */
	function onkeydown(event) {
		if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
			event.preventDefault();
			ask(draft);
		}
	}

	/**
	 * Says yes to a held time. The hold's token is the confirmation the agent
	 * books on; a "yes" typed in the box never books.
	 * @param {{ hold_token: string, starts_at: string }} hold
	 */
	function confirmHold(hold) {
		ask(t('Yes, please book {time}.', { time: formatDateTime(hold.starts_at) }), hold.hold_token);
	}
</script>

<div
	class={[
		'flex flex-col overflow-hidden rounded-card border border-line bg-surface shadow-card',
		className
	].join(' ')}
>
	<div class="flex items-center gap-3 border-b border-line px-4 py-3">
		<span
			class="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent"
		>
			<Icon name="sparkles" class="size-4" />
		</span>
		<div class="min-w-0">
			<p class="truncate font-semibold text-fg">{title ?? t('Assistant')}</p>
			{#if subtitle}<p class="truncate text-xs text-fg-muted">{subtitle}</p>{/if}
		</div>
	</div>

	<div bind:this={scroller} class="flex-1 space-y-4 overflow-y-auto p-4" aria-live="polite">
		{#if messages.length === 0}
			<div class="flex h-full flex-col items-center justify-center gap-4 text-center">
				<p class="max-w-sm text-sm text-fg-muted">
					{intro ?? t('Ask a question in your own words. Answers come from your live data.')}
				</p>
				{#if starters.length}
					<div class="flex max-w-xl flex-wrap justify-center gap-2">
						{#each starters as starter (starter)}
							<button
								type="button"
								class="rounded-full border border-line bg-surface px-3 py-1.5 text-start text-sm text-fg-secondary focus-ring transition-colors duration-fast hover:border-line-strong hover:text-fg"
								onclick={() => ask(starter)}
							>
								{starter}
							</button>
						{/each}
					</div>
				{/if}
			</div>
		{/if}

		{#each messages as message, index (index)}
			{#if message.role === 'user'}
				<div class="flex justify-end">
					<p
						class="max-w-[85%] rounded-card rounded-se-sm bg-brand-600 px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-line text-white"
					>
						{message.text}
					</p>
				</div>
			{:else}
				{@const r = message.response}
				<div class="flex flex-col items-start gap-2">
					<div
						class="max-w-[85%] rounded-card rounded-ss-sm border border-line bg-surface-sunken px-3.5 py-2.5 text-sm leading-relaxed text-fg"
					>
						<p class="whitespace-pre-line">{message.text}</p>
						{#if r?.degraded}
							<div class="mt-2">
								<Badge tone="warning" size="sm">{t('Fallback answer')}</Badge>
							</div>
						{/if}
					</div>

					{#if r}
						{#if r.requires_human_handoff}
							<Alert tone="warning" class="max-w-[85%]"
								>{t('A staff member will follow up on this.')}</Alert
							>
						{/if}

						{#each r.held_slots as hold (hold.hold_token)}
							<div
								class="flex w-full max-w-[85%] flex-wrap items-center justify-between gap-3 rounded-card border border-emerald-500/30 bg-emerald-50/70 px-3.5 py-3 text-sm dark:bg-emerald-500/10"
							>
								<div>
									<p class="font-medium text-fg">{formatDateTime(hold.starts_at)}</p>
									<p class="text-xs text-fg-muted">
										{t('Held for you — expires {when}', { when: formatRelative(hold.expires_at) })}
									</p>
								</div>
								{#if index === messages.length - 1 && !r.tickets.length}
									<Button size="sm" disabled={sending} onclick={() => confirmHold(hold)}
										>{t('Yes, book it')}</Button
									>
								{/if}
							</div>
						{/each}

						{#each r.tickets as ticket (ticket.ticket_id)}
							<TicketCard
								class="w-full max-w-sm"
								qrPayload={ticket.qr_payload}
								ticketCode={ticket.ticket_code}
								startsAt={ticket.starts_at}
								expiresAt={ticket.expires_at}
								businessName={ticket.business_name}
								status={ticket.booking_status}
							/>
						{/each}

						{#each r.queue_places as place (place.entry_id)}
							<Alert tone="info" class="max-w-[85%]">
								{t('Queue place #{place}', { place: place.place_in_line })}
								{place.estimated_wait_minutes !== null
									? ` — ${t('~{minutes} min', { minutes: place.estimated_wait_minutes })}`
									: ''}
							</Alert>
						{/each}

						{#each r.pending_cancellations as pending (pending.booking_id)}
							<Alert tone="warning" class="max-w-[85%]">
								{t('Cancel the booking on {time}? Confirm from your bookings list.', {
									time: formatDateTime(pending.starts_at)
								})}
								<a
									href={resolve('/bookings')}
									class="ms-1 font-semibold text-accent hover:underline">{t('My bookings')}</a
								>
							</Alert>
						{/each}

						{#if r.charts.length && tenantId}
							<div class="grid w-full grid-cols-1 gap-3 xl:grid-cols-2">
								{#each r.charts as chart (chart.chart_id + chart.generated_at)}
									<ChartPanel
										{tenantId}
										businessId={chart.business_id}
										{chart}
										currency={chart.currency}
									/>
								{/each}
							</div>
						{/if}

						{#if r.proposed_actions.length}
							<div class="grid w-full grid-cols-1 gap-2 md:grid-cols-2">
								{#each r.proposed_actions as action (action.id)}
									<div class="rounded-card border border-line bg-surface p-3.5 shadow-card">
										<div class="flex items-start gap-2">
											<Icon name="zap" class="mt-0.5 size-4 shrink-0 text-accent" />
											<div class="min-w-0">
												<p class="text-sm font-semibold text-fg">{action.title}</p>
												<p class="mt-1 text-[13px] text-fg-secondary">{action.rationale}</p>
												<p class="mt-2 text-xs text-fg-muted">
													{t('Based on: {metric}', { metric: action.metric })}
												</p>
											</div>
										</div>
										<p class="mt-2 text-xs text-fg-subtle">
											{t('A proposal only — nothing has been changed.')}
										</p>
									</div>
								{/each}
							</div>
						{/if}

						{#if r.suggested_actions.length && index === messages.length - 1 && !sending}
							<div class="flex max-w-[85%] flex-wrap gap-2">
								{#each r.suggested_actions as suggestion (suggestion)}
									<button
										type="button"
										class="rounded-full border border-line bg-surface px-3 py-1 text-[13px] text-fg-secondary focus-ring transition-colors duration-fast hover:border-line-strong hover:text-fg"
										onclick={() => ask(suggestion)}
									>
										{suggestion}
									</button>
								{/each}
							</div>
						{/if}
					{/if}
				</div>
			{/if}
		{/each}

		{#if sending}
			<div class="flex items-center gap-2 text-sm text-fg-muted" role="status">
				<span class="flex gap-1" aria-hidden="true">
					<span class="size-1.5 animate-bounce rounded-full bg-fg-subtle"></span>
					<span class="size-1.5 animate-bounce rounded-full bg-fg-subtle [animation-delay:150ms]"
					></span>
					<span class="size-1.5 animate-bounce rounded-full bg-fg-subtle [animation-delay:300ms]"
					></span>
				</span>
				{t('Thinking… {seconds}s', { seconds: elapsed })}
				{#if elapsed >= 20}
					<span class="text-xs text-fg-subtle"
						>{t('Local models can take a few minutes on a computer without a GPU.')}</span
					>
				{/if}
			</div>
		{/if}
	</div>

	{#if error}
		<div class="px-4 pb-2"><Alert tone="error">{error}</Alert></div>
	{/if}

	<form class="flex items-end gap-2 border-t border-line bg-surface-sunken p-3" onsubmit={submit}>
		<label class="sr-only" for={`${sessionId}-draft`}>{t('Message')}</label>
		<textarea
			id={`${sessionId}-draft`}
			bind:value={draft}
			{onkeydown}
			rows="1"
			maxlength="4000"
			placeholder={t('Type a message…')}
			disabled={sending}
			class="max-h-40 min-h-10 flex-1 resize-none rounded-control border border-line bg-surface px-3 py-2 text-sm text-fg focus-ring placeholder:text-fg-subtle disabled:opacity-60"
			style="field-sizing: content"></textarea>
		<Button type="submit" size="icon" disabled={!draft.trim()} loading={sending}>
			<Icon name="arrow-up" class="size-4" />
			<span class="sr-only">{t('Send')}</span>
		</Button>
	</form>
</div>
