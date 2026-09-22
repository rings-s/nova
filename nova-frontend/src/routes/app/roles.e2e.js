import { expect, test } from '@playwright/test';

// What the dashboard shows each role, against a stubbed API. The role comes
// from `GET /memberships/me` (the business's membership row), never from the
// token's `roles`, which merges every business the user works at — so the
// token below deliberately claims "owner" while the business says otherwise.

const TENANT = 'tenant-roles';
const BUSINESS = 'business-roles';
const cors = { 'access-control-allow-origin': '*' };

/** @param {object} value */
const base64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

const ACCESS = {
	owner: {
		role: 'owner',
		permissions: [
			'manage_catalog',
			'manage_subscription',
			'refund_payments',
			'view_analytics',
			'view_financials'
		],
		manageable_roles: ['manager', 'owner', 'provider', 'receptionist']
	},
	receptionist: { role: 'receptionist', permissions: [], manageable_roles: [] }
};

/**
 * @param {import('@playwright/test').Page} page
 * @param {keyof typeof ACCESS} role
 * @returns {Promise<string[]>} the API paths the page called
 */
async function signInAs(page, role) {
	const now = Math.floor(Date.now() / 1000);
	const token = [
		base64url({ alg: 'HS256', typ: 'JWT' }),
		base64url({
			sub: 'user-1',
			kind: 'staff',
			tenants: [TENANT],
			roles: ['owner'], // flattened across businesses: must not decide anything here
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
		calls.push(path);
		if (path === `/tenants/${TENANT}/memberships/me`) {
			return route.fulfill({ headers: cors, json: ACCESS[role] });
		}
		if (path === '/tenants') {
			return route.fulfill({
				headers: cors,
				json: { items: [{ id: TENANT, name_en: 'Roles Salon', name_ar: 'صالون' }] }
			});
		}
		if (path.endsWith(`/businesses/${BUSINESS}/locations`)) {
			return route.fulfill({
				headers: cors,
				json: {
					items: [
						{
							id: 'loc-1',
							business_id: BUSINESS,
							name_en: 'Olaya Branch',
							name_ar: 'فرع العليا',
							city: 'Riyadh',
							phone: '+966500000001',
							timezone: 'Asia/Riyadh',
							latitude: 24.7,
							longitude: 46.7
						}
					]
				}
			});
		}
		return route.fulfill({ headers: cors, json: { items: [] } });
	});
	return calls;
}

const nav = (/** @type {import('@playwright/test').Page} */ page) =>
	page.getByRole('navigation', { name: 'Dashboard' });

test.use({ viewport: { width: 1280, height: 900 } });

test('an owner sees every section and can edit the catalog', async ({ page }) => {
	await signInAs(page, 'owner');
	await page.goto('/app/catalog');

	await expect(nav(page).getByRole('link', { name: 'Analytics' })).toBeVisible();
	await expect(nav(page).getByRole('link', { name: 'Billing' })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Add location' })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Move pin' })).toBeVisible();
});

test.describe('a receptionist', () => {
	test('does not see the money sections, whatever the token claims', async ({ page }) => {
		await signInAs(page, 'receptionist');
		await page.goto('/app');

		await expect(nav(page).getByRole('link', { name: 'Customers' })).toBeVisible();
		await expect(nav(page).getByRole('link', { name: 'Analytics' })).toHaveCount(0);
		await expect(nav(page).getByRole('link', { name: 'Billing' })).toHaveCount(0);
		await expect(page.getByRole('complementary').getByText('Receptionist')).toBeVisible();
	});

	test('reads the catalog but cannot change it', async ({ page }) => {
		await signInAs(page, 'receptionist');
		await page.goto('/app/catalog');

		await expect(page.getByText('Olaya Branch')).toBeVisible();
		await expect(page.getByRole('button', { name: 'Add location' })).toHaveCount(0);
		await expect(page.getByRole('button', { name: 'Move pin' })).toHaveCount(0);
	});

	test('opening billing by its address explains instead of erroring, and asks for nothing', async ({
		page
	}) => {
		const calls = await signInAs(page, 'receptionist');
		await page.goto('/app/billing');

		await expect(page.getByText("You don't have access to billing")).toBeVisible();
		expect(calls.some((path) => path.includes('/billing/'))).toBe(false);
	});
});
