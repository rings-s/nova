<script>
	import { t, m } from '$lib/i18n/index.svelte.js';
	/**
	 * Follow-ups: customers an AI agent promised a person would get back to.
	 * The chat assistants open one when they hand off, and Sara when she
	 * tells a caller someone will call them back. Holds the customer's
	 * contact and their own words, so this needs `view_customers`, like the
	 * call log.
	 */
	import { resolve } from '$app/paths';
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { accessStore } from '$lib/stores/access.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { listFollowUps, resolveFollowUp } from '$lib/api/support.js';
	import { errorMessage } from '$lib/utils/errors.js';
	import { formatDateTime, formatRelative } from '$lib/utils/datetime.js';

	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import NoAccess from '$lib/components/ui/NoAccess.svelte';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Tabs from '$lib/components/ui/Tabs.svelte';

	let tenantId = $derived(tenantStore.activeTenantId);
	let allowed = $derived(accessStore.can('view_customers'));

	const limit = 20;
	let status = $state(/** @type {'open'|'resolved'} */ ('open'));
	let offset = $state(0);
	let loading = $state(true);
	let loadError = $state(/** @type {string|null} */ (null));
	let followUps = $state(/** @type {import('$lib/api/support.js').FollowUp[]} */ ([]));
	let resolving = $state(/** @type {string|null} */ (null));

	$effect(() => {
		if (!tenantId || !allowed) {
			loading = false;
			return;
		}
		const tenant = tenantId;
		const query = { status, limit, offset };
		let cancelled = false;
		loading = true;
		loadError = null;
		listFollowUps(tenant, query)
			.then((page) => {
				if (!cancelled) followUps = page.items;
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

	/** @type {Record<string, string>} */
	const REASONS = {
		escalated: m('The assistant handed it to you'),
		agent_could_not_help: m('The assistant could not help'),
		assistant_unavailable: m('The assistant was unavailable'),
		code_not_sent: m('Could not send the verification code'),
		cancellation_failed: m('A cancellation by phone failed'),
		call_too_long: m('The call ran too long')
	};

	/** @param {'open'|'resolved'} next */
	function show(next) {
		status = next;
		offset = 0;
	}

	/** @param {import('$lib/api/support.js').FollowUp} followUp */
	async function markResolved(followUp) {
		if (!tenantId) return;
		resolving = followUp.id;
		try {
			await resolveFollowUp(tenantId, followUp.id);
			followUps = followUps.filter((item) => item.id !== followUp.id);
			toastStore.success(t('Marked as resolved.'));
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			resolving = null;
		}
	}
</script>

<svelte:head><title>{t('Follow-ups')} — NOVA</title></svelte:head>

<PageHeader
	eyebrow={t('Operate')}
	title={t('Follow-ups')}
	subtitle={t(
		'Customers the AI assistant or Sara promised someone would get back to. Contact them, then mark it resolved.'
	)}
/>

{#if !allowed}
	<NoAccess what={t('follow-ups')} />
{:else}
	<div class="mb-4">
		<Tabs
			tabs={[
				{ id: 'open', label: t('Waiting') },
				{ id: 'resolved', label: t('Resolved') }
			]}
			active={status}
			onchange={(id) => show(/** @type {'open'|'resolved'} */ (id))}
		/>
	</div>

	{#if loadError}
		<Alert tone="error">{loadError}</Alert>
	{:else if loading && followUps.length === 0}
		<div class="space-y-3">
			{#each [0, 1, 2] as n (n)}<Skeleton class="h-24 rounded-card" />{/each}
		</div>
	{:else if followUps.length === 0}
		<EmptyState
			title={status === 'open' ? t('Nobody is waiting on you') : t('Nothing resolved yet')}
			description={status === 'open'
				? t('When an assistant hands a customer to your team, they appear here.')
				: t('Follow-ups you mark as resolved are kept here.')}
		>
			{#snippet icon()}<Icon name="inbox" class="size-6" />{/snippet}
		</EmptyState>
	{:else}
		<ul class="flex flex-col gap-3">
			{#each followUps as followUp (followUp.id)}
				<li class="rounded-card border border-line bg-surface p-5 shadow-card">
					<div class="flex flex-wrap items-start justify-between gap-3">
						<div class="min-w-0">
							<p class="font-medium text-fg">
								{followUp.contact_name ?? t('Unknown caller')}
							</p>
							<p class="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-fg-muted">
								{#if followUp.contact_phone}
									<a
										href={`tel:${followUp.contact_phone}`}
										class="inline-flex items-center gap-1 hover:text-fg"
										dir="ltr"><Icon name="phone" class="size-3.5" />{followUp.contact_phone}</a
									>
								{/if}
								{#if followUp.contact_email}
									<a href={`mailto:${followUp.contact_email}`} class="hover:text-fg" dir="ltr"
										>{followUp.contact_email}</a
									>
								{/if}
							</p>
						</div>
						<div class="flex flex-wrap items-center gap-2">
							<Badge size="sm">
								{followUp.source === 'call' ? t('Phone call') : t('Chat')}
							</Badge>
							<Badge tone={followUp.status === 'open' ? 'warning' : 'success'} dot>
								{followUp.status === 'open' ? t('Waiting') : t('Resolved')}
							</Badge>
						</div>
					</div>

					<p class="mt-3 text-sm font-medium text-fg">
						{REASONS[followUp.reason] ?? followUp.reason}
					</p>
					{#if followUp.summary}
						<p class="mt-1 text-sm text-fg">{followUp.summary}</p>
					{/if}
					{#if followUp.customer_message}
						<blockquote class="mt-2 border-s-2 border-line ps-3 text-sm text-fg-muted">
							<span class="sr-only">{t('The customer said:')}</span>
							{followUp.customer_message}
						</blockquote>
					{/if}

					<div class="mt-4 flex flex-wrap items-center justify-between gap-3">
						<p class="text-xs text-fg-muted" title={formatDateTime(followUp.opened_at)}>
							{followUp.status === 'open'
								? t('Waiting since {when}', { when: formatRelative(followUp.opened_at) })
								: t('Resolved {when}', {
										when: formatRelative(followUp.resolved_at ?? followUp.opened_at)
									})}
						</p>
						<div class="flex flex-wrap items-center gap-2">
							{#if followUp.customer_id}
								<Button
									variant="ghost"
									size="sm"
									href={resolve('/app/customers/[id]', { id: followUp.customer_id })}
								>
									{t('View customer')}
								</Button>
							{/if}
							{#if followUp.status === 'open'}
								<Button
									size="sm"
									variant="secondary"
									loading={resolving === followUp.id}
									disabled={resolving !== null}
									onclick={() => markResolved(followUp)}
								>
									<Icon name="check" class="size-4" />
									{t('Mark resolved')}
								</Button>
							{/if}
						</div>
					</div>
				</li>
			{/each}
		</ul>
		<div class="mt-6">
			<Pagination
				{limit}
				{offset}
				itemCount={followUps.length}
				onchange={(next) => (offset = next)}
			/>
		</div>
	{/if}
{/if}
