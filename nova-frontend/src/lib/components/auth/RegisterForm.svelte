<script>
	import { untrack } from 'svelte';
	/**
	 * Registration has no "role" of its own at the backend — `POST /auth/register`
	 * (identity/schemas.py::RegisterRequest) takes only email/password/full_name/phone.
	 * `MembershipRole` (owner/manager/receptionist/provider) exists only once someone
	 * belongs to a tenant, via an invite or by creating one. The only membership a
	 * brand-new account can reach by itself is "owner of a business it just created"
	 * (`createTenant`), so that's the one choice this form actually offers: register
	 * as a customer, or register and create a business (becoming its owner).
	 *
	 * Phone is required for the customer path even though `RegisterRequest`
	 * itself treats it as optional: a self-service booking needs a phone on
	 * the account before it can create the customer record behind it
	 * (`customer_phone_required` — "add a phone number... so the salon can
	 * reach you"), and there is nowhere later in this flow to add one, so the
	 * account itself is unusable for booking without it.
	 *
	 * Registering alone doesn't return a session (`RegisterRequest` -> `UserOut`,
	 * no tokens), so this logs in right after, and — for the owner path — creates
	 * the tenant (the account) and, on top of it, a `catalog.Business` (the
	 * public storefront profile — docs/06: "Business: tenant-level business
	 * profile"; a bare tenant has nowhere to hang a location or a service),
	 * then refreshes the token so it carries the new membership before
	 * calling back. The business id is cached client-side (`businessStore`) —
	 * there is no endpoint to list a tenant's businesses back later.
	 */
	import Icon from '../ui/Icon.svelte';
	import Input from '../ui/Input.svelte';
	import Button from '../ui/Button.svelte';
	import Alert from '../ui/Alert.svelte';
	import { authStore } from '../../stores/auth.svelte.js';
	import { tenantStore } from '../../stores/tenant.svelte.js';
	import { businessStore } from '../../stores/business.svelte.js';
	import { createTenant } from '../../api/identity.js';
	import { createBusiness } from '../../api/catalog.js';
	import { formatApiError } from '../../utils/errors.js';

	/**
	 * @type {{
	 *   onsuccess?: (
	 *     user: import('../../api/auth.js').RegisteredUser,
	 *     details: {
	 *       intent: 'customer'|'business_owner',
	 *       tenant?: import('../../api/identity.js').Tenant,
	 *       business?: import('../../api/catalog.js').Business
	 *     }
	 *   ) => void,
	 *   initialIntent?: 'customer'|'business_owner'|null
	 * }}
	 */
	let { onsuccess, initialIntent = null } = $props();

	/**
	 * Which kind of account. Deliberately no default when the page gives none:
	 * a silent "customer" default is how owners ended up with customer accounts
	 * and no way into the dashboard. Business sign-up links pass
	 * `?as=business`, customer ones `?as=customer`.
	 * @type {'customer'|'business_owner'|null}
	 */
	let intent = $state(untrack(() => initialIntent));

	/**
	 * The business-owner path alone has enough fields to earn a second,
	 * nested level of tabs — splitting the account credentials from the
	 * business's own details. Free to click between (someone fixing a typo
	 * shouldn't have to step through a wizard), so `handleSubmit` re-checks
	 * both groups regardless of which one is on screen when Submit is
	 * pressed — a jump straight to "Your business" must not silently submit
	 * blank account fields just because they're not the mounted, `required`
	 * inputs at that moment.
	 * @type {'account'|'business'}
	 */
	let businessSubTab = $state('account');

	let fullName = $state('');
	let email = $state('');
	let phone = $state('');
	let password = $state('');
	let businessNameEn = $state('');
	let businessNameAr = $state('');
	let businessPhone = $state('');

	let error = $state(/** @type {string|null} */ (null));
	let loading = $state(false);

	function isAccountStepValid() {
		return fullName.trim() !== '' && email.trim() !== '' && password.trim() !== '';
	}

	function goToBusinessStep() {
		if (!isAccountStepValid()) {
			error = 'Fill in your name, email and password first.';
			return;
		}
		error = null;
		businessSubTab = 'business';
	}

	/** @param {SubmitEvent} event */
	async function handleSubmit(event) {
		event.preventDefault();
		error = null;

		if (intent === null) {
			error = 'Choose whether this is a customer or a business account.';
			return;
		}
		if (intent === 'business_owner') {
			if (!isAccountStepValid()) {
				businessSubTab = 'account';
				error = 'Fill in your name, email and password first.';
				return;
			}
			if (!businessNameEn.trim() || !businessNameAr.trim() || !businessPhone.trim()) {
				businessSubTab = 'business';
				error = "Fill in your business's name and phone.";
				return;
			}
		}

		loading = true;
		try {
			const user = await authStore.register({ email, password, fullName, phone: phone || null });
			await authStore.login({ email, password });

			if (intent === 'business_owner') {
				const tenant = await createTenant({
					nameEn: businessNameEn,
					nameAr: businessNameAr,
					phone: businessPhone
				});
				// The token minted at login carries no membership yet — this
				// tenant was created after it. Re-mint so it does, before the
				// next call (creating the business) needs tenant-scoped access.
				await authStore.refreshSession();
				const business = await createBusiness(tenant.id, {
					nameEn: businessNameEn,
					nameAr: businessNameAr
				});
				tenantStore.set(tenant.id);
				businessStore.set(tenant.id, business.id);
				onsuccess?.(user, { intent, tenant, business });
			} else {
				onsuccess?.(user, { intent: 'customer' });
			}
		} catch (err) {
			error = formatApiError(err);
		} finally {
			loading = false;
		}
	}

	/** @type {{ id: string, label: string, hint: string, icon: import('../ui/Icon.svelte').IconName }[]} */
	const intentOptions = [
		{ id: 'customer', label: 'Customer', hint: 'Book and join queues', icon: 'user' },
		{ id: 'business_owner', label: 'Business', hint: 'List a salon or spa', icon: 'building' }
	];
</script>

<form class="flex flex-col gap-4" onsubmit={handleSubmit}>
	{#if error}
		<Alert tone="error">{error}</Alert>
	{/if}

	<fieldset class="flex flex-col gap-2">
		<legend class="mb-2 text-sm font-medium text-fg-secondary">I'm signing up as a</legend>
		<div class="grid grid-cols-2 gap-2">
			{#each intentOptions as option (option.id)}
				<label
					class={[
						'relative flex cursor-pointer flex-col gap-1 rounded-card border p-3 transition-[border-color,box-shadow] duration-fast has-[:focus-visible]:ring-4 has-[:focus-visible]:ring-brand-500/20',
						intent === option.id
							? 'border-brand-500 bg-accent-soft/60 ring-4 ring-brand-500/10'
							: 'border-line-strong hover:border-fg-subtle'
					].join(' ')}
				>
					<input
						type="radio"
						name="intent"
						value={option.id}
						class="sr-only"
						bind:group={intent}
						onchange={() => (businessSubTab = 'account')}
					/>
					<Icon
						name={option.icon}
						class={`size-5 ${intent === option.id ? 'text-accent' : 'text-fg-subtle'}`}
					/>
					<span class="text-sm font-semibold text-fg">{option.label}</span>
					<span class="text-xs text-fg-muted">{option.hint}</span>
				</label>
			{/each}
		</div>
	</fieldset>

	{#if intent === 'customer'}
		<Input label="Full name" required autocomplete="name" bind:value={fullName} />
		<Input type="email" label="Email" required autocomplete="email" bind:value={email} />
		<Input
			type="tel"
			label="Phone"
			required
			hint="A GCC number — needed to book, so the salon can reach you."
			autocomplete="tel"
			bind:value={phone}
		/>
		<Input
			type="password"
			label="Password"
			required
			hint="At least 12 characters."
			autocomplete="new-password"
			bind:value={password}
		/>

		<Button type="submit" {loading} fullWidth>Create account</Button>
	{:else if intent === 'business_owner'}
		<div class="flex flex-col gap-4">
			<ol class="flex items-center gap-2 text-xs font-medium" aria-label="Sign-up steps">
				{#each [{ id: 'account', label: 'Your account' }, { id: 'business', label: 'Your business' }] as stepItem, index (stepItem.id)}
					{#if index > 0}<li class="h-px flex-1 bg-line" aria-hidden="true"></li>{/if}
					<li>
						<button
							type="button"
							onclick={() =>
								stepItem.id === 'account' ? (businessSubTab = 'account') : goToBusinessStep()}
							aria-current={businessSubTab === stepItem.id ? 'step' : undefined}
							class={[
								'inline-flex items-center gap-2 rounded-full py-1 ps-1 pe-3 focus-ring transition-colors',
								businessSubTab === stepItem.id ? 'text-fg' : 'text-fg-muted hover:text-fg'
							].join(' ')}
						>
							<span
								class={[
									'flex size-6 items-center justify-center rounded-full text-[11px] font-semibold',
									businessSubTab === stepItem.id
										? 'bg-brand-600 text-white'
										: 'border border-line-strong text-fg-muted'
								].join(' ')}
							>
								{index + 1}
							</span>
							{stepItem.label}
						</button>
					</li>
				{/each}
			</ol>

			{#if businessSubTab === 'account'}
				<Input label="Full name" required autocomplete="name" bind:value={fullName} />
				<Input type="email" label="Email" required autocomplete="email" bind:value={email} />
				<Input
					type="tel"
					label="Phone"
					hint="Optional — a GCC number."
					autocomplete="tel"
					bind:value={phone}
				/>
				<Input
					type="password"
					label="Password"
					required
					hint="At least 12 characters."
					autocomplete="new-password"
					bind:value={password}
				/>
				<Button type="button" variant="outline" fullWidth onclick={goToBusinessStep}>
					Continue to your business
					<Icon name="arrow-right" class="size-4 rtl:rotate-180" />
				</Button>
			{:else}
				<div class="grid gap-4 sm:grid-cols-2">
					<Input label="Business name (English)" required bind:value={businessNameEn} />
					<Input label="Business name (Arabic)" required dir="rtl" bind:value={businessNameAr} />
				</div>
				<Input type="tel" label="Business phone" required bind:value={businessPhone} />
				<Button
					type="button"
					variant="ghost"
					size="sm"
					onclick={() => (businessSubTab = 'account')}
				>
					<Icon name="chevron-left" class="size-4 rtl:rotate-180" />
					Back to your account
				</Button>
			{/if}
		</div>

		<Button type="submit" {loading} fullWidth>Create account and business</Button>
	{:else}
		<p class="text-center text-sm text-fg-muted">Choose the kind of account to continue.</p>
	{/if}
</form>
