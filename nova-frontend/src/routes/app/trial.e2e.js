import { expect, test } from '@playwright/test';

// The dashboard during a business's free week, and once it ends unpaid, against
// a stubbed API (`StandingOut` in nova_backend/app/modules/billing/schemas.py).

const TENANT = 'tenant-trial';
const BUSINESS = 'business-trial';
const cors = { 'access-control-allow-origin': '*' };

/** @param {object} value */
const base64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

const TRIALING = {
	business_id: BUSINESS,
	has_plan: true,
	tier: 'studio',
	status: 'trialing',
	trialing: true,
	trial_ends_at: '2026-10-14',
	trial_ai_messages_left: 7,
	locked: false
};

const LOCKED = {
	...TRIALING,
	status: 'pending_payment',
	trialing: false,
	trial_ai_messages_left: null,
	locked: true
};

/**
 * @param {import('@playwright/test').Page} page
 * @param {{ standing: object, role?: string, permissions?: string[] }} options
 */
async function signIn(page, { standing, role = 'owner', permissions }) {
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
			return json({
				role,
				permissions: permissions ?? ['view_financials', 'manage_subscription'],
				manageable_roles: []
			});
		}
		if (path === '/tenants') {
			return json({ items: [{ id: TENANT, name_en: 'Trial Spa', name_ar: 'سبا' }] });
		}
		if (path.endsWith(`/billing/subscriptions/${BUSINESS}/standing`)) return json(standing);
		return json({ items: [], total: 0 });
	});
}

test.use({ viewport: { width: 1280, height: 900 } });

test('during the free week, every page says when it ends and what is left', async ({ page }) => {
	await signIn(page, { standing: TRIALING });
	await page.goto('/app');

	await expect(page.getByText('Free trial of Studio until Oct 13, 2026.')).toBeVisible();
	await expect(page.getByText('7 of 10 AI messages left.')).toBeVisible();
	await expect(page.getByRole('link', { name: 'Pay now' })).toHaveAttribute(
		'href',
		'/app/billing/checkout'
	);
});

test('once the week ends unpaid, the owner is sent to Billing', async ({ page }) => {
	await signIn(page, { standing: LOCKED });
	await page.goto('/app/bookings');

	await expect(page).toHaveURL(/\/app\/billing$/);
});

test('a receptionist of a locked business sees why, not a broken page', async ({ page }) => {
	await signIn(page, { standing: LOCKED, role: 'receptionist', permissions: ['view_customers'] });
	await page.goto('/app/bookings');

	await expect(page.getByRole('heading', { name: 'Your free trial has ended' })).toBeVisible();
	await expect(
		page.getByText('Ask the business owner to pay for the plan to unlock the dashboard.')
	).toBeVisible();
	await expect(page).toHaveURL(/\/app\/bookings$/);
});
