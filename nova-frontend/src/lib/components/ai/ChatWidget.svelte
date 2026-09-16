<script>
	/**
	 * One conversation with a NOVA agent (docs/13). A tool's write — a held
	 * slot, a queue place — is already committed by the time a reply comes
	 * back, even if `requires_human_handoff` is true, so `held_slots` and
	 * `queue_places` are shown regardless. No agent cancels: a
	 * `pending_cancellations` entry still needs the customer to confirm
	 * through `cancelBooking` (booking.js) themselves.
	 */
	import { sendChatMessage } from '../../api/ai.js';
	import { formatDateTime, formatRelative } from '../../utils/datetime.js';
	import Input from '../ui/Input.svelte';
	import Button from '../ui/Button.svelte';
	import Badge from '../ui/Badge.svelte';
	import Alert from '../ui/Alert.svelte';
	import Spinner from '../ui/Spinner.svelte';
	import { errorMessage } from '../../utils/errors.js';

	/**
	 * @type {{
	 *   tenantId: string,
	 *   agent?: string,
	 *   businessId?: string|null,
	 *   customerId?: string|null,
	 *   locale?: 'en'|'ar',
	 *   title?: string
	 * }}
	 */
	let {
		tenantId,
		agent = 'concierge_agent',
		businessId = null,
		customerId = null,
		locale = 'ar',
		title = 'Chat'
	} = $props();

	const sessionId = crypto.randomUUID();

	/**
	 * @typedef {{ role: 'user'|'assistant', text: string, response?: import('../../api/ai.js').AiChatResponse }} ChatMessage
	 */
	let messages = $state(/** @type {ChatMessage[]} */ ([]));
	let draft = $state('');
	let sending = $state(false);
	let error = $state(/** @type {string|null} */ (null));

	/** @param {SubmitEvent} event */
	async function send(event) {
		event.preventDefault();
		const text = draft.trim();
		if (!text || sending) return;

		messages = [...messages, { role: 'user', text }];
		draft = '';
		sending = true;
		error = null;

		try {
			const response = await sendChatMessage(tenantId, {
				sessionId,
				message: text,
				locale,
				businessId,
				customerId,
				agent
			});
			messages = [...messages, { role: 'assistant', text: response.reply, response }];
		} catch (err) {
			error = errorMessage(err);
		} finally {
			sending = false;
		}
	}
</script>

<div
	class="flex h-[32rem] flex-col rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
>
	<div class="border-b border-slate-200 px-4 py-3 dark:border-slate-800">
		<p class="font-medium text-slate-900 dark:text-slate-100">{title}</p>
	</div>

	<div class="flex-1 space-y-3 overflow-y-auto p-4">
		{#each messages as message, index (index)}
			<div class={message.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
				<div
					class={[
						'max-w-[85%] rounded-lg px-3 py-2 text-sm',
						message.role === 'user'
							? 'bg-brand-600 text-white'
							: 'bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-slate-100'
					].join(' ')}
				>
					<p>{message.text}</p>

					{#if message.response}
						{@const r = message.response}
						{#if r.degraded}
							<Badge tone="warning" size="sm">Fallback answer</Badge>
						{/if}
						{#if r.requires_human_handoff}
							<Alert tone="warning" class="mt-2">A staff member will follow up on this.</Alert>
						{/if}
						{#each r.held_slots as hold (hold.hold_token)}
							<Alert tone="success" class="mt-2">
								Slot held: {formatDateTime(hold.starts_at, locale)} — expires
								{formatRelative(hold.expires_at, locale)}
							</Alert>
						{/each}
						{#each r.queue_places as place (place.entry_id)}
							<Alert tone="info" class="mt-2">
								Queue place #{place.place_in_line}
								{place.estimated_wait_minutes !== null
									? ` — ~${place.estimated_wait_minutes} min`
									: ''}
							</Alert>
						{/each}
						{#each r.pending_cancellations as pending (pending.booking_id)}
							<Alert tone="warning" class="mt-2">
								Cancel the booking on {formatDateTime(pending.starts_at, locale)}? Confirm from your
								bookings list.
							</Alert>
						{/each}
						{#if r.proposed_actions.length > 0}
							<div class="mt-2 flex flex-col gap-1">
								{#each r.proposed_actions as action (action.id)}
									<Badge tone="accent" size="sm">{action.title}</Badge>
								{/each}
							</div>
						{/if}
					{/if}
				</div>
			</div>
		{/each}
		{#if sending}
			<div class="flex justify-start"><Spinner size="sm" /></div>
		{/if}
	</div>

	{#if error}
		<div class="px-4"><Alert tone="error">{error}</Alert></div>
	{/if}

	<form class="flex gap-2 border-t border-slate-200 p-3 dark:border-slate-800" onsubmit={send}>
		<div class="flex-1">
			<Input bind:value={draft} placeholder="Type a message…" disabled={sending} />
		</div>
		<Button type="submit" disabled={!draft.trim()} loading={sending}>Send</Button>
	</form>
</div>
