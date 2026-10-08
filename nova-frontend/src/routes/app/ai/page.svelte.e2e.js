import { expect, test } from '@playwright/test';

// The staff AI workspace against a stubbed API: which agents a plan unlocks
// (`nova_backend/app/modules/billing/domain.py` PLANS, `ai_agents/agents.py`).

const TENANT = 'tenant-ai';
const BUSINESS = 'business-ai';
const cors = { 'access-control-allow-origin': '*' };
const INSIGHTS = 'ai_insights_agent';

/** @param {object} value */
const base64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

/** @param {string} tier @param {string[]} included_features */
const plan = (tier, included_features) => ({
	tier,
	monthly_price: { free: '0.00', solo: '400.00', studio: '600.00', chain: '1200.00' }[tier],
	annual_price: null,
	currency: 'SAR',
	new_client_commission_pct: '30.00',
	repeat_commission_pct: '0',
	processing_fee_pct: '2.5',
	included_features,
	priced_per_location: false,
	max_seats: null,
	max_locations: 1,
	whatsapp_reminders_per_month: null,
	contract_months: 0
});

const PLANS = [
	plan('free', ['ai_booking_agent', 'ai_support_agent']),
	plan('solo', ['ai_booking_agent', 'ai_support_agent']),
	plan('studio', ['ai_booking_agent', 'ai_support_agent', INSIGHTS]),
	plan('chain', ['ai_booking_agent', 'ai_support_agent', INSIGHTS])
];

/** @param {string} name @param {string|null} required_feature @param {string} permission */
const agent = (name, required_feature, permission) => ({
	name,
	audience: 'staff',
	goal: name,
	required_feature,
	required_permission: permission,
	needs_business: true
});

const CATALOG = {
	inference_available: true,
	available: ['accountant_agent', 'analyst_agent', 'business_manager_agent'],
	aliases: {},
	agents: [
		agent('accountant_agent', null, 'view_financials'),
		agent('analyst_agent', INSIGHTS, 'view_analytics'),
		agent('business_manager_agent', INSIGHTS, 'view_analytics')
	]
};

/**
 * @param {import('@playwright/test').Page} page
 * @param {{ subscription: object|null, role?: 'owner'|'manager' }} options
 */
async function openAi(page, { subscription, role = 'owner' }) {
	const permissions =
		role === 'owner'
			? ['view_financials', 'view_analytics', 'manage_subscription']
			: ['view_financials', 'view_analytics'];
	const now = Math.floor(Date.now() / 1000);
	const token = [
		base64url({ alg: 'HS256', typ: 'JWT' }),
		base64url({
			sub: 'user-1',
			kind: 'staff',
			tenants: [TENANT],
			roles: [role],
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
		const json = (/** @type {object} */ value, status = 200) =>
			route.fulfill({ status, headers: cors, json: value });

		if (path === `/tenants/${TENANT}/memberships/me`) {
			return json({ role, permissions, manageable_roles: [] });
		}
		if (path === '/tenants') {
			return json({ items: [{ id: TENANT, name_en: 'AI Spa', name_ar: 'سبا' }] });
		}
		if (path.endsWith('/ai/agents')) return json(CATALOG);
		if (path.endsWith('/billing/plans')) return json({ items: PLANS, total: 3 });
		if (path.endsWith(`/billing/subscriptions/${BUSINESS}`)) {
			return subscription
				? json(subscription)
				: json({ error: { code: 'not_found', message: 'No subscription.' } }, 404);
		}
		return json({ items: [], total: 0 });
	});

	await page.goto('/app/ai');
	await expect(page.getByRole('button', { name: /Accountant/ })).toBeVisible();
}

/** @param {string} tier @param {string} status */
const subscription = (tier, status = 'active') => ({
	id: 'sub-1',
	business_id: BUSINESS,
	tier,
	status
});

test.use({ viewport: { width: 1280, height: 900 } });

test('on Free, the insights agents are locked and point to the upgrade', async ({ page }) => {
	await openAi(page, { subscription: null });

	// The accountant comes with every plan: a chat, not a lock.
	await expect(page.getByPlaceholder('Type a message…')).toBeVisible();

	await page.getByRole('button', { name: /Analyst/ }).click();
	await expect(page.getByText('Analyst comes with Studio')).toBeVisible();
	await expect(page.getByPlaceholder('Type a message…')).toBeHidden();
	await expect(page.getByRole('link', { name: 'Upgrade to Studio' })).toHaveAttribute(
		'href',
		'/app/billing?plan=studio'
	);
});

test('a Studio plan waiting on its first payment is still Free here', async ({ page }) => {
	await openAi(page, { subscription: subscription('studio', 'pending_payment') });

	await page.getByRole('button', { name: /Business manager/ }).click();
	await expect(page.getByText('Business manager comes with Studio')).toBeVisible();
});

for (const tier of ['studio', 'chain']) {
	test(`on ${tier}, every agent opens a chat`, async ({ page }) => {
		await openAi(page, { subscription: subscription(tier) });

		for (const name of [/Accountant/, /Analyst/, /Business manager/]) {
			await page.getByRole('button', { name }).click();
			await expect(page.getByPlaceholder('Type a message…')).toBeVisible();
			await expect(page.getByText(/comes with/)).toBeHidden();
		}
	});
}

test('a manager is told to ask the owner, with no upgrade button', async ({ page }) => {
	await openAi(page, { subscription: null, role: 'manager' });

	await page.getByRole('button', { name: /Analyst/ }).click();
	await expect(page.getByText('Ask the business owner to upgrade.')).toBeVisible();
	await expect(page.getByRole('link', { name: /Upgrade/ })).toHaveCount(0);
});
