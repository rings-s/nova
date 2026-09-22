import { expect, test } from '@playwright/test';

// Where signing in takes you, against a stubbed API: business staff to the
// dashboard, customers to the site, and anyone sent here from a page back to
// that page — but only a page on this site.

const TENANT = 'tenant-landing';
const cors = { 'access-control-allow-origin': '*' };

/** @param {object} value */
const base64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

/** @param {'staff'|'customer'} kind */
function tokenFor(kind) {
	const now = Math.floor(Date.now() / 1000);
	return [
		base64url({ alg: 'HS256', typ: 'JWT' }),
		base64url({
			sub: `user-${kind}`,
			kind,
			tenants: kind === 'staff' ? [TENANT] : [],
			roles: kind === 'staff' ? ['owner'] : [],
			iat: now,
			exp: now + 3600
		}),
		'signature'
	].join('.');
}

/** @param {import('@playwright/test').Page} page @param {'staff'|'customer'} kind */
async function stubApi(page, kind) {
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
		if (path === '/auth/login') {
			return route.fulfill({
				headers: cors,
				json: { access_token: tokenFor(kind), refresh_token: 'r', token_type: 'bearer' }
			});
		}
		if (path === `/tenants/${TENANT}/memberships/me`) {
			return route.fulfill({
				headers: cors,
				json: { role: 'owner', permissions: ['manage_catalog'], manageable_roles: [] }
			});
		}
		if (path === '/tenants') {
			return route.fulfill({ headers: cors, json: { items: [{ id: TENANT, name_en: 'Salon' }] } });
		}
		return route.fulfill({ headers: cors, json: { items: [] } });
	});
}

/** @param {import('@playwright/test').Page} page @param {string} [query] */
async function signIn(page, query = '') {
	await page.goto(`/login${query}`);
	// The form only works once the page's script is running.
	await page.waitForLoadState('networkidle');
	await page.getByLabel('Email').fill('someone@example.com');
	await page.getByLabel('Password').fill('a-long-password-123');
	await page.getByRole('button', { name: 'Sign in' }).last().click();
}

test.use({ viewport: { width: 1280, height: 900 } });

test('a business owner lands on the dashboard', async ({ page }) => {
	await stubApi(page, 'staff');
	await signIn(page);

	await expect(page).toHaveURL(/\/app$/);
	await expect(page.getByRole('navigation', { name: 'Dashboard' })).toBeVisible();
});

test('a customer lands on the site, not the dashboard', async ({ page }) => {
	await stubApi(page, 'customer');
	await signIn(page);

	await expect(page).toHaveURL(/\/$/);
});

test('a signed-out owner opening a dashboard page returns to it after signing in', async ({
	page
}) => {
	await stubApi(page, 'staff');
	await page.goto('/app/team');

	await expect(page).toHaveURL(/\/login\?next=%2Fapp%2Fteam$/);
	await page.waitForLoadState('networkidle');
	await page.getByLabel('Email').fill('someone@example.com');
	await page.getByLabel('Password').fill('a-long-password-123');
	await page.getByRole('button', { name: 'Sign in' }).last().click();

	await expect(page).toHaveURL(/\/app\/team$/);
});

test('an outside address in "next" is ignored', async ({ page }) => {
	await stubApi(page, 'staff');
	await signIn(page, '?next=' + encodeURIComponent('//evil.example/phish'));

	await expect(page).toHaveURL(/localhost:\d+\/app$/);
});

test('an owner who is already signed in skips the sign-in page', async ({ page }) => {
	await stubApi(page, 'staff');
	await page.addInitScript(
		(token) =>
			localStorage.setItem(
				'nova.auth.v1',
				JSON.stringify({ accessToken: token, refreshToken: 'r' })
			),
		tokenFor('staff')
	);
	await page.goto('/login');

	await expect(page).toHaveURL(/\/app$/);
});
