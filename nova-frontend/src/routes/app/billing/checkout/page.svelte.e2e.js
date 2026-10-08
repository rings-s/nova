import { expect, test } from '@playwright/test';

// The plan checkout against a stubbed API, in the shape the real endpoint
// returns (`CheckoutOut` in nova_backend/app/modules/billing/schemas.py).

const TENANT = 'tenant-checkout';
const BUSINESS = 'business-checkout';
const cors = { 'access-control-allow-origin': '*' };

/** @param {object} value */
const base64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

const STUDIO = {
	tier: 'studio',
	monthly_price: '199.00',
	annual_price: '1990.00',
	currency: 'SAR',
	new_client_commission_pct: '30.00',
	repeat_commission_pct: '0',
	processing_fee_pct: '2.5',
	included_features: ['marketplace_profile', 'calendar', 'ai_insights_agent'],
	priced_per_location: false,
	max_seats: null,
	max_locations: 1,
	whatsapp_reminders_per_month: null,
	contract_months: 0
};

const CHECKOUT = {
	id: 'checkout-1',
	business_id: BUSINESS,
	tier: 'studio',
	annual: false,
	status: 'pending',
	net_amount: '199.00',
	vat_amount: '29.85',
	total_amount: '228.85',
	currency: 'SAR',
	covers_from: '2026-10-01',
	covers_until: '2026-11-01',
	paid_at: null,
	redirect_url: 'https://checkout.moyasar.com/invoices/inv_1',
	checkout: {
		publishable_api_key: 'pk_test_e2e',
		invoice_id: 'inv_1',
		amount: 22885,
		currency: 'SAR',
		description: 'NOVA studio plan',
		callback_url: 'http://localhost:5173/app/billing?checkout=checkout-1'
	}
};

/**
 * @param {import('@playwright/test').Page} page
 * @param {{ checkout?: { status: number, json: object } }} [options]
 * @returns {Promise<{ method: string, path: string }[]>}
 */
async function signIn(page, options = {}) {
	const now = Math.floor(Date.now() / 1000);
	const token = [
		base64url({ alg: 'HS256', typ: 'JWT' }),
		base64url({
			sub: 'user-1',
			kind: 'staff',
			tenants: [TENANT],
			roles: ['owner'],
			iat: now,
			exp: now + 3600
		}),
		'signature'
	].join('.');
	await page.addInitScript(
		([accessToken, tenant, business]) => {
			localStorage.setItem('nova.auth.v1', JSON.stringify({ accessToken, refreshToken: 'r' }));
			localStorage.setItem('nova.activeTenantId', tenant);
			localStorage.setItem('nova.businessByTenant', JSON.stringify({ [tenant]: business }));
		},
		[token, TENANT, BUSINESS]
	);

	/** @type {{ method: string, path: string }[]} */ const calls = [];
	await page.route('**/api/v1/**', (route) => {
		const request = route.request();
		if (request.method() === 'OPTIONS') {
			return route.fulfill({
				status: 204,
				headers: {
					...cors,
					'access-control-allow-headers': '*',
					'access-control-allow-methods': '*'
				}
			});
		}
		const path = new URL(request.url()).pathname.replace(/^.*\/api\/v1/, '');
		calls.push({ method: request.method(), path });
		const json = (/** @type {object} */ value, status = 200) =>
			route.fulfill({ status, headers: cors, json: value });

		if (path === `/tenants/${TENANT}/memberships/me`) {
			return json({
				role: 'owner',
				permissions: ['view_financials', 'manage_subscription'],
				manageable_roles: []
			});
		}
		if (path === '/tenants') {
			return json({ items: [{ id: TENANT, name_en: 'Checkout Spa', name_ar: 'سبا' }] });
		}
		if (path.endsWith('/billing/plans')) return json({ items: [STUDIO], total: 1 });
		if (path.endsWith(`/billing/subscriptions/${BUSINESS}/checkout`)) {
			const answer = options.checkout ?? { status: 201, json: CHECKOUT };
			return json(answer.json, answer.status);
		}
		if (path.endsWith(`/billing/subscriptions/${BUSINESS}`)) {
			return json({
				id: 'sub-1',
				business_id: BUSINESS,
				tier: 'studio',
				status: 'trialing',
				trial_ends_at: '2026-10-14',
				trial_ai_messages_left: 10,
				locked: false,
				current_period_start: '2026-10-01',
				current_period_end: '2026-11-01',
				seats: 1,
				locations: 1,
				cancel_at_period_end: false,
				annual: false,
				monthly_amount: '199.00',
				currency: 'SAR',
				marketplace_listing_hidden: false
			});
		}
		return json({ items: [], total: 0 });
	});
	return calls;
}

test.use({ viewport: { width: 1280, height: 900 } });

test('the plan is paid in NOVA’s own checkout, with what is bought spelled out', async ({
	page
}) => {
	await signIn(page);
	await page.goto('/app/billing/checkout');

	await expect(page.getByRole('heading', { name: 'Checkout' })).toBeVisible();
	await expect(page.getByText('Studio plan')).toBeVisible();
	await expect(page.getByText('Oct 1, 2026 – Oct 31, 2026')).toBeVisible();
	await expect(page.getByText('SAR 29.85')).toBeVisible();
	await expect(page.getByText('SAR 228.85')).toBeVisible();
	await expect(page.getByText('AI business insights')).toBeVisible();
	await expect(page.getByText('Payment details')).toBeVisible();
	// Moyasar's form renders into NOVA's themed wrapper, on this page.
	await expect(page.locator('.nova-pay')).toBeVisible();
	expect(page.url()).toContain('/app/billing/checkout');
});

test('pay now on the billing page opens the checkout page', async ({ page }) => {
	const calls = await signIn(page);
	await page.goto('/app/billing');

	await page.getByRole('button', { name: 'Pay now' }).click();

	await expect(page).toHaveURL(/\/app\/billing\/checkout$/);
	await expect(page.getByText('SAR 228.85')).toBeVisible();
	expect(calls.filter((c) => c.path.endsWith('/checkout'))).toHaveLength(1);
});

test('with nothing to pay, the page says so instead of failing', async ({ page }) => {
	await signIn(page, {
		checkout: {
			status: 409,
			json: {
				error: {
					code: 'subscription_not_awaiting_payment',
					message: 'Nothing to pay.',
					field: null,
					retryable: false
				}
			}
		}
	});
	await page.goto('/app/billing/checkout');

	await expect(page.getByText('Nothing to pay right now')).toBeVisible();
	await expect(page.getByRole('link', { name: 'Back to billing' }).last()).toBeVisible();
});
