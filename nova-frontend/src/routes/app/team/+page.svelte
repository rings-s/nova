<script>
	/**
	 * Staff roster and invites. Everyday work (calendar, queue, check-in) is
	 * open to any active member — only who's on the roster, at what rank, is
	 * gated here, and even then the actual rank check happens server-side
	 * (CLAUDE.md: "never decided from `Principal.roles`") — a receptionist who
	 * tries to invite or promote just gets the 403 back.
	 *
	 * The invite token is the entire credential and is shown here exactly
	 * once, at creation — NOVA never delivers it, so it's on the inviter to
	 * relay it out of band.
	 */
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { authStore } from '$lib/stores/auth.svelte.js';
	import { accessStore } from '$lib/stores/access.svelte.js';
	import { toastStore } from '$lib/stores/toast.svelte.js';
	import { formatApiError, errorMessage } from '$lib/utils/errors.js';
	import { formatDate } from '$lib/utils/datetime.js';
	import {
		listMemberships,
		inviteMembership,
		listPendingInvites,
		changeMembershipRole,
		revokeMembership
	} from '$lib/api/identity.js';

	import Icon from '$lib/components/ui/Icon.svelte';
	import Avatar from '$lib/components/ui/Avatar.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Spinner from '$lib/components/ui/Spinner.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';

	let tenantId = $derived(/** @type {string} */ (tenantStore.activeTenantId));

	/** @type {{ value: import('$lib/api/identity.js').MembershipRole, label: string }[]} */
	const ROLE_OPTIONS = [
		{ value: 'owner', label: 'Owner' },
		{ value: 'manager', label: 'Manager' },
		{ value: 'receptionist', label: 'Receptionist' },
		{ value: 'provider', label: 'Provider' }
	];

	// What this person may do here, from their membership in this business. An
	// owner manages everyone; a manager only receptionists and providers;
	// anyone else just sees the roster. The server enforces the same rule.
	let canInvite = $derived(accessStore.manageableRoles.length > 0);
	let grantableOptions = $derived(
		ROLE_OPTIONS.filter((option) => accessStore.canManage(option.value))
	);
	let myUserId = $derived(String(authStore.principal?.sub ?? ''));

	let loading = $state(true);
	let loadErrorMessage = $state(/** @type {string|null} */ (null));
	let members = $state(/** @type {import('$lib/api/identity.js').Membership[]} */ ([]));
	let invites = $state(
		/** @type {import('$lib/api/identity.js').MembershipInviteSummary[]} */ ([])
	);

	/** Per-row role selection, separate from `members` so a change needs an explicit Save.
	 * @type {Record<string, string>} */
	let roleDrafts = $state({});

	async function loadAll() {
		loading = true;
		loadErrorMessage = null;
		try {
			const [membersPage, invitesPage] = await Promise.all([
				listMemberships(tenantId, { limit: 50 }),
				listPendingInvites(tenantId, { limit: 50 })
			]);
			members = membersPage.items;
			invites = invitesPage.items;
			roleDrafts = Object.fromEntries(members.map((m) => [m.id, m.role]));
		} catch (err) {
			loadErrorMessage = errorMessage(err);
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (tenantId) loadAll();
	});

	// --- Invite ------------------------------------------------------------------

	let inviteModalOpen = $state(false);
	let inviting = $state(false);
	let inviteError = $state(/** @type {string|null} */ (null));
	let inviteForm = $state({ email: '', role: /** @type {string} */ ('receptionist') });
	let issuedInvite = $state(
		/** @type {import('$lib/api/identity.js').MembershipInvite|null} */ (null)
	);

	/** @param {SubmitEvent} event */
	async function handleInvite(event) {
		event.preventDefault();
		inviteError = null;
		inviting = true;
		try {
			const invite = await inviteMembership(tenantId, {
				email: inviteForm.email,
				role: /** @type {import('$lib/api/identity.js').MembershipRole} */ (inviteForm.role)
			});
			issuedInvite = invite;
			inviteForm = { email: '', role: 'receptionist' };
			inviteModalOpen = false;
			await loadAll();
		} catch (err) {
			inviteError = formatApiError(err);
		} finally {
			inviting = false;
		}
	}

	async function copyInviteToken() {
		if (!issuedInvite) return;
		try {
			await navigator.clipboard?.writeText(issuedInvite.token);
			toastStore.success('Invite token copied.');
		} catch {
			toastStore.error('Could not copy — select and copy it manually.');
		}
	}

	// --- Role change ---------------------------------------------------------------

	let savingRoleId = $state(/** @type {string|null} */ (null));

	/** @param {import('$lib/api/identity.js').Membership} member */
	async function saveRole(member) {
		const nextRole = /** @type {import('$lib/api/identity.js').MembershipRole} */ (
			roleDrafts[member.id]
		);
		if (!nextRole || nextRole === member.role) return;
		savingRoleId = member.id;
		try {
			const updated = await changeMembershipRole(tenantId, member.id, nextRole);
			members = members.map((m) => (m.id === updated.id ? updated : m));
			roleDrafts = { ...roleDrafts, [updated.id]: updated.role };
			toastStore.success(`${updated.full_name}'s role is now ${updated.role}.`);
		} catch (err) {
			toastStore.fromError(err);
			roleDrafts = { ...roleDrafts, [member.id]: member.role };
		} finally {
			savingRoleId = null;
		}
	}

	// --- Revoke ------------------------------------------------------------------

	let revokeTarget = $state(/** @type {import('$lib/api/identity.js').Membership|null} */ (null));
	let revoking = $state(false);

	async function confirmRevoke() {
		const target = revokeTarget;
		if (!target) return;
		revoking = true;
		try {
			await revokeMembership(tenantId, target.id);
			members = members.filter((m) => m.id !== target.id);
			toastStore.success(`Revoked ${target.full_name}'s access.`);
			revokeTarget = null;
		} catch (err) {
			toastStore.fromError(err);
		} finally {
			revoking = false;
		}
	}
</script>

<svelte:head><title>Team — NOVA</title></svelte:head>

<PageHeader
	eyebrow="Business"
	title="Team"
	subtitle="Who has access to this business, and at what rank."
>
	{#snippet actions()}
		{#if canInvite}
			<Button onclick={() => (inviteModalOpen = true)}>
				<Icon name="plus" class="size-4" />
				Invite someone
			</Button>
		{/if}
	{/snippet}
</PageHeader>

{#if issuedInvite}
	<Alert tone="success" class="mb-4" dismissible ondismiss={() => (issuedInvite = null)}>
		<p>
			Invite created for <strong>{issuedInvite.email}</strong> ({issuedInvite.role}). Send this
			token to them yourself — NOVA won't, and it won't be shown again.
		</p>
		<div class="mt-3 flex items-center gap-2">
			<code
				class="h-8 flex-1 truncate rounded-control border border-emerald-200 bg-surface px-3 font-mono text-xs leading-8 text-fg dark:border-emerald-500/20"
				>{issuedInvite.token}</code
			>
			<Button size="sm" variant="outline" onclick={copyInviteToken}>Copy</Button>
		</div>
	</Alert>
{/if}

{#if loading}
	<div class="flex justify-center py-12"><Spinner /></div>
{:else if loadErrorMessage}
	<Alert tone="error">{loadErrorMessage}</Alert>
{:else}
	<section class="mb-10">
		<h2 class="mb-3 text-base font-semibold tracking-tight text-fg">
			Members <span class="ms-1 text-sm font-normal text-fg-muted">{members.length}</span>
		</h2>
		{#if members.length === 0}
			<EmptyState title="No members yet">
				{#snippet icon()}<Icon name="users" class="size-6" />{/snippet}
			</EmptyState>
		{:else}
			<Card padding="none">
				<div class="divide-y divide-line-subtle">
					{#each members as member (member.id)}
						<div class="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5">
							<div class="flex min-w-0 items-center gap-3">
								<Avatar name={member.full_name} />
								<div class="min-w-0">
									<p class="truncate text-sm font-medium text-fg">{member.full_name}</p>
									<p class="truncate text-xs text-fg-muted">{member.email}</p>
								</div>
							</div>
							{#if !accessStore.canManage(member.role) || member.user_id === myUserId}
								<Badge tone={member.role === 'owner' ? 'accent' : 'neutral'} size="sm">
									{member.role.replace(/^\w/, (c) => c.toUpperCase())}{member.user_id === myUserId
										? ' · you'
										: ''}
								</Badge>
							{:else}
								<div class="flex items-center gap-2">
									<div class="w-36">
										<Select
											aria-label={`Role for ${member.full_name}`}
											bind:value={roleDrafts[member.id]}
											options={grantableOptions}
										/>
									</div>
									<Button
										size="sm"
										variant="outline"
										disabled={roleDrafts[member.id] === member.role}
										loading={savingRoleId === member.id}
										onclick={() => saveRole(member)}
									>
										Save
									</Button>
									<Button size="sm" variant="danger-ghost" onclick={() => (revokeTarget = member)}>
										Revoke
									</Button>
								</div>
							{/if}
						</div>
					{/each}
				</div>
			</Card>
		{/if}
	</section>

	<section>
		<h2 class="mb-3 text-base font-semibold tracking-tight text-fg">Pending invites</h2>
		{#if invites.length === 0}
			<EmptyState
				title="No pending invites"
				description="Invites you send appear here until they're accepted."
			>
				{#snippet icon()}<Icon name="user-check" class="size-6" />{/snippet}
			</EmptyState>
		{:else}
			<Card padding="none">
				<div class="divide-y divide-line-subtle">
					{#each invites as invite (invite.id)}
						<div class="flex items-center justify-between gap-3 px-5 py-3.5">
							<div class="flex min-w-0 items-center gap-3">
								<span
									class="flex size-10 shrink-0 items-center justify-center rounded-full border border-dashed border-line-strong text-fg-subtle"
								>
									<Icon name="user" class="size-4" />
								</span>
								<div class="min-w-0">
									<p class="truncate text-sm font-medium text-fg">{invite.email}</p>
									<p class="text-xs text-fg-muted">
										Expires {formatDate(invite.expires_at, 'en')}
									</p>
								</div>
							</div>
							<Badge tone="info" size="sm">{invite.role}</Badge>
						</div>
					{/each}
				</div>
			</Card>
		{/if}
	</section>
{/if}

<Modal bind:open={inviteModalOpen} title="Invite someone">
	{#if inviteError}
		<Alert tone="error" class="mb-4">{inviteError}</Alert>
	{/if}
	<form class="flex flex-col gap-4" onsubmit={handleInvite}>
		<Input type="email" label="Email" required bind:value={inviteForm.email} />
		<Select label="Role" bind:value={inviteForm.role} options={grantableOptions} />
		<Button type="submit" loading={inviting} fullWidth>Send invite</Button>
	</form>
</Modal>

<Modal open={revokeTarget !== null} title="Revoke access" onclose={() => (revokeTarget = null)}>
	{#if revokeTarget}
		<p class="text-sm text-fg-secondary">
			Revoke <strong>{revokeTarget.full_name}</strong>'s access to this business? They'll be signed
			out everywhere and will need a new invite to come back.
		</p>
	{/if}
	{#snippet footer()}
		<Button variant="ghost" onclick={() => (revokeTarget = null)}>Cancel</Button>
		<Button variant="danger" loading={revoking} onclick={confirmRevoke}>Revoke access</Button>
	{/snippet}
</Modal>
