import { expect, test } from '@playwright/test';

// How an account becomes a business owner, against a stubbed API. The story
// behind it: owners who signed up with the account type left on "Customer"
// had no way into the dashboard.

const TENANT = 'tenant-new';
const cors = { 'access-control-allow-origin': '*' };
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

test('a customer who opens the dashboard is offered to list their business', async ({ page }) => {
	await signedInCustomer(page);
	await page.goto('/app');

	await expect(page).toHaveURL(/\/business\/new$/);
	await expect(page.getByRole('heading', { name: 'List your business' })).toBeVisible();
});

test('listing a business makes the account its owner and opens the dashboard', async ({ page }) => {
	const calls = await signedInCustomer(page);
	await page.goto('/business/new');
	await page.waitForLoadState('networkidle');

	await page.getByLabel('Business name (English)').fill('New Lounge');
	await page.getByLabel('Business name (Arabic)').fill('صالة جديدة');
	await page.getByLabel('Business phone').fill('+966500000010');
	await page.getByRole('button', { name: 'Create my business' }).click();

	await expect(page).toHaveURL(/\/app$/);
	await expect(page.getByRole('navigation', { name: 'Dashboard' })).toBeVisible();
	// Order matters: the storefront can only be created once the session knows
	// about the new membership.
	const order = [
		'POST /tenants',
		'POST /auth/refresh',
		`POST /tenants/${TENANT}/catalog/businesses`
	];
	expect(calls.filter((c) => order.includes(c))).toEqual(order);
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
