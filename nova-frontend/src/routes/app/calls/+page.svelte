<script>
	import { t, m } from '$lib/i18n/index.svelte.js';
	/**
	 * Calls with Sara, the AI agent who answers the business's phone
	 * (ADR-0017): who called, whether she checked it was really them, and
	 * what came of it. Callers' numbers are customer data, so this needs
	 * `view_customers`, like the customer pages.
	 */
	import { resolve } from '$app/paths';
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { accessStore } from '$lib/stores/access.svelte.js';
	import { listCalls } from '$lib/api/call_center.js';
	import { errorMessage } from '$lib/utils/errors.js';
	import { formatDateTime } from '$lib/utils/datetime.js';

	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import NoAccess from '$lib/components/ui/NoAccess.svelte';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';

	let tenantId = $derived(tenantStore.activeTenantId);
	let allowed = $derived(accessStore.can('view_customers'));

	const limit = 25;
	let offset = $state(0);
	let loading = $state(true);
	let loadError = $state(/** @type {string|null} */ (null));
	let calls = $state(/** @type {import('$lib/api/call_center.js').Call[]} */ ([]));

	$effect(() => {
		if (!tenantId || !allowed) {
			loading = false;
			return;
		}
		const tenant = tenantId;
		const page = offset;
		let cancelled = false;
		loading = true;
		loadError = null;
		listCalls(tenant, { limit, offset: page })
			.then((result) => {
				if (!cancelled) calls = result;
			})
			.catch((err) => {
				if (!cancelled) loadError = errorMessage(err);
			})
			.finally(() => {
				if (!cancelled) loading = false;
			});
		return () => {
			cancelled = true;
		};
	});

	/** @type {Record<string, { label: string, tone: 'neutral'|'success'|'warning'|'error'|'info'|'accent' }>} */
	const OUTCOMES = {
		booked: { label: m('Booked'), tone: 'success' },
		queued: { label: m('Joined the queue'), tone: 'success' },
		cancelled: { label: m('Cancelled a booking'), tone: 'neutral' },
		callback_requested: { label: m('Call back'), tone: 'warning' },
		reminder_kept: { label: m('Kept the appointment'), tone: 'success' },
		turn_limit: { label: m('Call too long'), tone: 'neutral' },
		unavailable: { label: m('Not on your plan'), tone: 'error' },
		no_answer: { label: m('No answer'), tone: 'neutral' }
	};

	/** @param {import('$lib/api/call_center.js').Call} call */
	function outcomeOf(call) {
		if (call.outcome) return OUTCOMES[call.outcome];
		return call.status === 'in_progress'
			? { label: t('In progress'), tone: /** @type {const} */ ('info') }
			: { label: t('Questions only'), tone: /** @type {const} */ ('neutral') };
	}
</script>

<svelte:head><title>{t('Calls')} — NOVA</title></svelte:head>

<PageHeader
	eyebrow={t('Operate')}
	title={t('Calls')}
	subtitle={t(
		'Sara answers your phone: she books, adds walk-ins to the queue, and rings customers who agreed to reminder calls.'
	)}
/>

{#if !allowed}
	<NoAccess what={t('the call log')} />
{:else if loadError}
	<Alert tone="error">{loadError}</Alert>
{:else if loading && calls.length === 0}
	<div class="space-y-3">
		{#each [0, 1, 2] as n (n)}<Skeleton class="h-20 rounded-card" />{/each}
	</div>
{:else if calls.length === 0}
	<EmptyState
		title={t('No calls yet')}
		description={t(
			'Once NOVA connects a phone number to your business, every call Sara takes appears here.'
		)}
	>
		{#snippet icon()}<Icon name="phone" class="size-6" />{/snippet}
	</EmptyState>
{:else}
	<ul class="flex flex-col gap-3">
		{#each calls as call (call.id)}
			{@const outcome = outcomeOf(call)}
			<li class="rounded-card border border-line bg-surface p-5 shadow-card">
				<div class="flex flex-wrap items-center justify-between gap-2">
					<div class="flex min-w-0 items-center gap-2">
						<Icon name="phone" class="size-4 text-fg-muted" />
						<span class="font-medium text-fg" dir="ltr"
							>{call.caller_e164 ?? t('Hidden number')}</span
						>
						<Badge size="sm">
							{call.purpose === 'reminder' ? t('Reminder call') : t('Incoming')}
						</Badge>
					</div>
					<Badge tone={outcome.tone} dot>{outcome.label}</Badge>
				</div>
				<p class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-muted">
					<span>{formatDateTime(call.started_at)}</span>
					<span>{t('{n} turns', { n: call.turns })}</span>
					{#if call.verified}
						<span class="inline-flex items-center gap-1"
							><Icon name="shield-check" class="size-3.5" />{t('Caller verified')}</span
						>
					{/if}
				</p>
				{#if call.customer_id}
					<a
						href={resolve('/app/customers/[id]', { id: call.customer_id })}
						class="mt-3 inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
					>
						{t('View customer')}
						<Icon name="chevron-right" class="size-3.5 rtl:rotate-180" />
					</a>
				{/if}
			</li>
		{/each}
	</ul>
	<div class="mt-6">
		<Pagination {limit} {offset} itemCount={calls.length} onchange={(next) => (offset = next)} />
	</div>
{/if}
