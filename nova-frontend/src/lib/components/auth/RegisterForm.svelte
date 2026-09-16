<script>
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
	import Input from '../ui/Input.svelte';
	import Button from '../ui/Button.svelte';
	import Alert from '../ui/Alert.svelte';
	import Tabs from '../ui/Tabs.svelte';
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
	 *   ) => void
	 * }}
	 */
	let { onsuccess } = $props();

	/** @type {'customer'|'business_owner'} */
	let intent = $state('customer');

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
				onsuccess?.(user, { intent });
			}
		} catch (err) {
			error = formatApiError(err);
		} finally {
			loading = false;
		}
	}
</script>

<form class="flex flex-col gap-4" onsubmit={handleSubmit}>
	{#if error}
		<Alert tone="error">{error}</Alert>
	{/if}

	<div class="flex flex-col gap-1">
		<span class="text-sm font-medium text-slate-700 dark:text-slate-200">I'm signing up as a</span>
		<Tabs
			tabs={[
				{ id: 'customer', label: 'Customer' },
				{ id: 'business_owner', label: 'Business owner' }
			]}
			bind:active={intent}
			onchange={() => (businessSubTab = 'account')}
		/>
		<p class="pt-1 text-xs text-slate-500 dark:text-slate-400">
			{intent === 'customer'
				? 'Book appointments and join queues.'
				: 'List a salon or spa on NOVA — you become its owner.'}
		</p>
	</div>

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
	{:else}
		<div class="flex flex-col gap-4 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
			<Tabs
				tabs={[
					{ id: 'account', label: 'Your account' },
					{ id: 'business', label: 'Your business' }
				]}
				bind:active={businessSubTab}
			/>

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
					Continue to your business →
				</Button>
			{:else}
				<Input label="Business name (English)" required bind:value={businessNameEn} />
				<Input label="Business name (Arabic)" required dir="rtl" bind:value={businessNameAr} />
				<Input type="tel" label="Business phone" required bind:value={businessPhone} />
				<Button
					type="button"
					variant="ghost"
					size="sm"
					onclick={() => (businessSubTab = 'account')}
				>
					← Back to your account
				</Button>
			{/if}
		</div>

		<Button type="submit" {loading} fullWidth>Create account and business</Button>
	{/if}
</form>
