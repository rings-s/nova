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

<PageHeader title="Team" subtitle="Who has access to this business, and at what rank." />

{#if issuedInvite}
	<Alert tone="success" class="mb-4" dismissible ondismiss={() => (issuedInvite = null)}>
		<p>
			Invite created for <strong>{issuedInvite.email}</strong> ({issuedInvite.role}). Send this
			token to them yourself — NOVA won't, and it won't be shown again.
		</p>
		<div class="mt-2 flex items-center gap-2">
			<code
				class="flex-1 truncate rounded-md bg-emerald-100 px-2 py-1 text-xs text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100"
				>{issuedInvite.token}</code
			>
			<Button size="sm" variant="outline" onclick={copyInviteToken}>Copy</Button>
		</div>
	</Alert>
{/if}

<div class="mb-4 flex justify-end">
	<Button onclick={() => (inviteModalOpen = true)}>Invite someone</Button>
</div>

{#if loading}
	<div class="flex justify-center py-12"><Spinner /></div>
{:else if loadErrorMessage}
	<Alert tone="error">{loadErrorMessage}</Alert>
{:else}
	<section class="mb-8">
		<h2 class="mb-3 font-medium text-slate-900 dark:text-slate-100">Members</h2>
		{#if members.length === 0}
			<EmptyState title="No members yet" />
		{:else}
			<Card padding="none">
				<div class="divide-y divide-slate-100 dark:divide-slate-800">
					{#each members as member (member.id)}
						<div class="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
							<div class="min-w-0">
								<p class="text-sm font-medium text-slate-900 dark:text-slate-100">
									{member.full_name}
								</p>
								<p class="text-xs text-slate-500 dark:text-slate-400">{member.email}</p>
							</div>
							<div class="flex items-center gap-2">
								<div class="w-40">
									<Select bind:value={roleDrafts[member.id]} options={ROLE_OPTIONS} />
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
								<Button size="sm" variant="danger" onclick={() => (revokeTarget = member)}>
									Revoke
								</Button>
							</div>
						</div>
					{/each}
				</div>
			</Card>
		{/if}
	</section>

	<section>
		<h2 class="mb-3 font-medium text-slate-900 dark:text-slate-100">Pending invites</h2>
		{#if invites.length === 0}
			<EmptyState title="No pending invites" />
		{:else}
			<Card padding="none">
				<div class="divide-y divide-slate-100 dark:divide-slate-800">
					{#each invites as invite (invite.id)}
						<div class="flex items-center justify-between px-4 py-3">
							<div>
								<p class="text-sm font-medium text-slate-900 dark:text-slate-100">{invite.email}</p>
								<p class="text-xs text-slate-500 dark:text-slate-400">
									Expires {formatDate(invite.expires_at, 'en')}
								</p>
							</div>
							<Badge tone="info">{invite.role}</Badge>
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
		<Select label="Role" bind:value={inviteForm.role} options={ROLE_OPTIONS} />
		<Button type="submit" loading={inviting} fullWidth>Send invite</Button>
	</form>
</Modal>

<Modal open={revokeTarget !== null} title="Revoke access" onclose={() => (revokeTarget = null)}>
	{#if revokeTarget}
		<p class="text-sm text-slate-700 dark:text-slate-200">
			Revoke <strong>{revokeTarget.full_name}</strong>'s access to this business? They'll be signed
			out everywhere and will need a new invite to come back.
		</p>
	{/if}
	{#snippet footer()}
		<Button variant="ghost" onclick={() => (revokeTarget = null)}>Cancel</Button>
		<Button variant="danger" loading={revoking} onclick={confirmRevoke}>Revoke access</Button>
	{/snippet}
</Modal>
