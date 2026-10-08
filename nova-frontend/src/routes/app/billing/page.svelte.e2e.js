import { expect, test } from '@playwright/test';

// The billing page against a stubbed API, in the shape the real endpoints
// return (`nova_backend/app/modules/billing/schemas.py`).

const TENANT = 'tenant-billing';
const BUSINESS = 'business-billing';
const cors = { 'access-control-allow-origin': '*' };

/** @param {object} value */
const base64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

/** @param {string} tier @param {object} [extra] */
const plan = (tier, extra = {}) => ({
	tier,
	monthly_price: '0.00',
	annual_price: null,
	currency: 'SAR',
	new_client_commission_pct: '35.00',
	repeat_commission_pct: '0',
	processing_fee_pct: '2.5',
	included_features: ['marketplace_profile', 'calendar'],
	priced_per_location: false,
	max_seats: 1,
	max_locations: 1,
	whatsapp_reminders_per_month: 100,
	contract_months: 0,
	...extra
});

const PLANS = [
	plan('free'),
	plan('solo', { monthly_price: '400.00', annual_price: '4000.00' }),
	plan('studio', {
		monthly_price: '600.00',
		annual_price: '6000.00',
		new_client_commission_pct: '30.00',
		included_features: ['marketplace_profile', 'calendar', 'ai_insights_agent'],
		max_seats: null,
		whatsapp_reminders_per_month: null
	}),
	plan('chain', {
		monthly_price: '1200.00',
		annual_price: '12000.00',
		new_client_commission_pct: '25.00',
		included_features: ['marketplace_profile', 'calendar', 'ai_insights_agent', 'api_access'],
		priced_per_location: true,
		max_seats: null,
		max_locations: null,
		whatsapp_reminders_per_month: null,
		contract_months: 12
	})
];

const SUBSCRIPTION = {
	id: 'sub-1',
	business_id: BUSINESS,
	tier: 'studio',
	status: 'active',
	current_period_start: '2026-09-01',
	current_period_end: '2026-10-01',
	seats: 3,
	locations: 2,
	cancel_at_period_end: false,
	annual: false,
	monthly_amount: '600.00',
	currency: 'SAR',
	marketplace_listing_hidden: false
};

const INVOICE = {
	id: 'inv-1',
	business_id: BUSINESS,
	period_start: '2026-08-01',
	period_end: '2026-09-01',
	status: 'overdue',
	subscription_amount: '199.00',
	commission_amount: '144.00',
	processing_amount: '12.00',
	vat_amount: '53.25',
	total_amount: '408.25',
	currency: 'SAR',
	issued_at: '2026-09-01T06:00:00Z',
	due_at: '2026-09-15',
	paid_at: null,
	lines_url: ''
};

/**
 * @param {import('@playwright/test').Page} page
 * @param {{ permissions?: string[], path?: string, changePlan?: (body: any) => { status: number, json: object } }} [options]
 * @returns {Promise<{ method: string, path: string, body: any }[]>} the API calls the page made
 */
async function openBilling(page, options = {}) {
	const permissions = options.permissions ?? ['view_financials', 'manage_subscription'];
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

	/** @type {{ method: string, path: string, body: any }[]} */ const calls = [];
	let subscription = { ...SUBSCRIPTION };
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
		const body = request.postDataJSON();
		calls.push({ method: request.method(), path, body });
		const json = (/** @type {object} */ value, status = 200) =>
			route.fulfill({ status, headers: cors, json: value });

		if (path === `/tenants/${TENANT}/memberships/me`) {
			return json({ role: 'owner', permissions, manageable_roles: [] });
		}
		if (path === '/tenants') {
			return json({ items: [{ id: TENANT, name_en: 'Billing Spa', name_ar: 'سبا' }] });
		}
		if (path.endsWith('/billing/plans')) return json({ items: PLANS, total: 3 });
		if (path.endsWith(`/billing/subscriptions/${BUSINESS}`)) return json(subscription);
		if (path.endsWith(`/billing/subscriptions/${BUSINESS}/plan`)) {
			const answer = options.changePlan?.(body);
			if (answer) return json(answer.json, answer.status);
			subscription = { ...subscription, tier: body.tier, annual: body.annual };
			return json(subscription);
		}
		if (path.endsWith(`/billing/subscriptions/${BUSINESS}/cancel`)) {
			subscription = { ...subscription, cancel_at_period_end: true };
			return json(subscription);
		}
		if (path.endsWith('/billing/invoices')) return json({ items: [INVOICE], total: 1 });
		if (path.endsWith('/lines')) {
			return json({
				items: [
					{
						id: 'line-1',
						booking_id: 'b-1',
						source: 'marketplace',
						commission_class: 'new_marketplace',
						base_amount: '480.00',
						rate_pct: '30.00',
						amount: '144.00',
						currency: 'SAR',
						reversed: false,
						status: 'invoiced',
						is_reversal: false,
						accrued_at: '2026-08-04T10:00:00Z'
					}
				]
			});
		}
		if (path.endsWith('/explain')) {
			return json({ reason: 'A first visit that came from the marketplace.' });
		}
		return json({ items: [], total: 0 });
	});

	await page.goto(options.path ?? '/app/billing');
	await expect(page.getByRole('heading', { name: 'Studio', exact: true }).first()).toBeVisible();
	return calls;
}

test.use({ viewport: { width: 1280, height: 900 } });

test('the plan shows its room, and an overdue invoice is flagged', async ({ page }) => {
	await openBilling(page);

	const current = page.getByRole('region', { name: 'Studio' }).first();
	await expect(current).toContainText('3 of unlimited');
	// More branches than the plan allows (a business moved onto it) still reads plainly.
	await expect(current).toContainText('2 of 1');
	// The period is half-open: it covers up to the day before Oct 1.
	await expect(current.getByText('Sep 1 – Sep 30, 2026')).toBeVisible();
	await expect(page.getByText('The August 2026 invoice is overdue.')).toBeVisible();
	await expect(page.getByRole('region', { name: 'Due to NOVA' })).toContainText('SAR 408.25');
});

test('an upgrade is confirmed first, showing what changes', async ({ page }) => {
	const calls = await openBilling(page);

	await page.getByRole('button', { name: 'Upgrade to Chain' }).click();
	const dialog = page.getByRole('dialog', { name: 'Upgrade to Chain?' });
	await expect(dialog.getByText('SAR 1,200 / month per branch')).toBeVisible();
	// Priced per branch: two branches make it 2,400.
	await expect(dialog.getByText('SAR 2,400 a month for your 2 branches')).toBeVisible();
	await expect(dialog.getByText('12 months')).toBeVisible();
	// A year is per branch too, with two months free: 2 × 12,000.
	await dialog.getByLabel('Pay yearly (SAR 12,000 a year per branch)').check();
	await expect(dialog.getByText('SAR 24,000 a year for your 2 branches')).toBeVisible();
	await dialog.getByLabel('Pay yearly (SAR 12,000 a year per branch)').uncheck();
	expect(calls.some((c) => c.path.endsWith('/plan'))).toBe(false);

	await dialog.getByRole('button', { name: 'Confirm change' }).click();
	await expect(dialog).toBeHidden();
	expect(calls.find((c) => c.path.endsWith('/plan'))?.body).toEqual({
		tier: 'chain',
		annual: false
	});
	await expect(page.getByText('Your current plan')).toBeVisible();
});

test('a plan picked on the pricing page opens its confirmation', async ({ page }) => {
	await openBilling(page, { path: '/app/billing?plan=chain' });

	await expect(page.getByRole('dialog', { name: 'Upgrade to Chain?' })).toBeVisible();
	// Dropped from the URL, so a reload does not ask again.
	await expect(page).toHaveURL(/\/app\/billing$/);
});

test('a refused downgrade is explained in the dialog, not lost in a toast', async ({ page }) => {
	await openBilling(page, {
		changePlan: () => ({
			status: 409,
			json: {
				error: {
					code: 'downgrade_below_usage',
					message: 'The plan allows 1 locations; 2 are in use.',
					field: null,
					retryable: false
				}
			}
		})
	});

	await page.getByRole('button', { name: 'Move to Solo' }).click();
	const dialog = page.getByRole('dialog', { name: 'Move to Solo?' });
	await dialog.getByRole('button', { name: 'Confirm change' }).click();
	await expect(dialog.getByText('2 are in use')).toBeVisible();
});

test('yearly billing is offered where a plan has a yearly price', async ({ page }) => {
	const calls = await openBilling(page);

	await page.getByRole('radio', { name: /Yearly/ }).click();
	const studio = page.getByRole('article', { name: 'Studio' });
	await expect(studio.getByText('SAR 6,000')).toBeVisible();
	await expect(studio.getByText('2 months free')).toBeVisible();

	await studio.getByRole('button', { name: 'Switch to yearly' }).click();
	await page.getByRole('button', { name: 'Confirm change' }).click();
	expect(calls.find((c) => c.path.endsWith('/plan'))?.body).toEqual({
		tier: 'studio',
		annual: true
	});
});

test('cancelling asks first, and then says when the plan ends', async ({ page }) => {
	const calls = await openBilling(page);

	await page.getByRole('button', { name: 'Cancel plan' }).click();
	const dialog = page.getByRole('dialog', { name: 'Cancel your plan?' });
	await expect(dialog.getByText('Sep 30, 2026')).toBeVisible();
	await dialog.getByRole('button', { name: 'Keep my plan' }).click();
	expect(calls.some((c) => c.path.endsWith('/cancel'))).toBe(false);

	await page.getByRole('button', { name: 'Cancel plan' }).click();
	await page.getByRole('dialog').getByRole('button', { name: 'Cancel plan' }).click();
	expect(calls.find((c) => c.path.endsWith('/cancel'))?.body).toEqual({ at_period_end: true });
	await expect(page.getByText('Studio ends on Sep 30, 2026.')).toBeVisible();
});

test('an invoice opens to its charges and the reason behind each commission', async ({ page }) => {
	await openBilling(page);

	await page.getByRole('button', { name: 'August 2026' }).click();
	const dialog = page.getByRole('dialog', { name: 'Invoice · August 2026' });
	await expect(dialog.getByText('30% of SAR 480.00')).toBeVisible();
	await dialog.getByRole('button', { name: 'Why this rate?' }).click();
	await expect(dialog.getByText('A first visit that came from the marketplace.')).toBeVisible();
});

test('a manager reads billing but is offered nothing to change', async ({ page }) => {
	await openBilling(page, { permissions: ['view_financials'] });

	await expect(page.getByText('Only the business owner can change the plan.')).toBeVisible();
	await expect(page.getByRole('button', { name: 'Cancel plan' })).toHaveCount(0);
	await expect(page.getByRole('button', { name: /Upgrade to|Move to/ })).toHaveCount(0);
});
