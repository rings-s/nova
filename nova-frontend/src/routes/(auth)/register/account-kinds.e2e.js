import { expect, test } from '@playwright/test';

// How an account becomes a business owner, against a stubbed API. The story
// behind it: owners who signed up with the account type left on "Customer"
// had no way into the dashboard.

const TENANT = 'tenant-new';
// As the real API answers: `/auth/*` is fetched with credentials (the refresh
// cookie), and a browser refuses a credentialed response to a wildcard origin.
const cors = {
	'access-control-allow-origin': new URL(process.env.E2E_BASE_URL ?? 'http://localhost:5173')
		.origin,
	'access-control-allow-credentials': 'true'
};
/** @param {object} value */
const base64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

/** @param {'staff'|'customer'} kind */
function token(kind) {
	const now = Math.floor(Date.now() / 1000);
	return [
		base64url({ alg: 'HS256', typ: 'JWT' }),
		base64url({
			sub: 'user-1',
			kind,
			tenants: kind === 'staff' ? [TENANT] : [],
			roles: kind === 'staff' ? ['owner'] : [],
			iat: now,
			exp: now + 3600
		}),
		'signature'
	].join('.');
}

/** @param {import('@playwright/test').Page} page */
async function signedInCustomer(page) {
	await page.addInitScript(
		(t) =>
			localStorage.setItem('nova.auth.v1', JSON.stringify({ accessToken: t, refreshToken: 'r' })),
		token('customer')
	);
	/** @type {string[]} */ const calls = [];
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
		calls.push(`${request.method()} ${path}`);
		const json = (/** @type {unknown} */ body, status = 200) =>
			route.fulfill({ status, headers: cors, json: body });
		if (request.method() === 'POST' && path === '/tenants') {
			return json({ id: TENANT, name_en: 'New Lounge', name_ar: 'صالة' }, 201);
		}
		// The re-issued session carries the new membership.
		if (path === '/auth/refresh') {
			return json({ access_token: token('staff'), refresh_token: 'r2', token_type: 'bearer' });
		}
		if (request.method() === 'POST' && path === `/tenants/${TENANT}/catalog/businesses`) {
			return json({ id: 'biz-new', tenant_id: TENANT, name_en: 'New Lounge' }, 201);
		}
		if (path === `/tenants/${TENANT}/memberships/me`) {
			return json({ role: 'owner', permissions: ['manage_catalog'], manageable_roles: [] });
		}
		if (path === '/tenants') return json({ items: [{ id: TENANT, name_en: 'New Lounge' }] });
		return json({ items: [] });
	});
	return calls;
}

test.use({ viewport: { width: 1280, height: 900 } });

test('a customer never sees the dashboard, and is not told about it', async ({ page }) => {
	await signedInCustomer(page);
	await page.goto('/app/bookings');

	await expect(page).toHaveURL(/\/$/);
	await expect(page.getByRole('link', { name: 'Dashboard' })).toHaveCount(0);
	await expect(page.getByText(/dashboard/i)).toHaveCount(0);
});

test('a customer is not offered to list a business', async ({ page }) => {
	await signedInCustomer(page);
	await page.goto('/');

	await expect(page.getByRole('link', { name: 'My bookings' }).first()).toBeVisible();
	await expect(page.getByRole('link', { name: 'List your business' })).toHaveCount(0);
});

test('business sign-up links choose the business account for you', async ({ page }) => {
	await page.goto('/register?as=business');

	await expect(page.getByRole('radio', { name: /Business/ })).toBeChecked();
	await expect(page.getByLabel('Full name')).toBeVisible();
});

test('a plain sign-up page asks which kind of account, instead of assuming', async ({ page }) => {
	await page.goto('/register');

	await expect(page.getByRole('radio', { name: /Customer/ })).not.toBeChecked();
	await expect(page.getByRole('radio', { name: /Business/ })).not.toBeChecked();
	await expect(page.getByText('Choose the kind of account to continue.')).toBeVisible();
	await expect(page.getByLabel('Full name')).toHaveCount(0);
});
