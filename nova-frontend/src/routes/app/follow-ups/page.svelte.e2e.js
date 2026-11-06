import { expect, test } from '@playwright/test';

// The follow-up inbox, against a stubbed API: who an assistant promised a
// person would get back to, and marking it done.

const TENANT = 'tenant-follow-ups';
const BUSINESS = 'business-follow-ups';
// `/auth/*` is fetched with credentials, and a browser refuses a wildcard
// origin on a credentialed response, so echo the page's own.
const cors = {
	'access-control-allow-origin': 'http://localhost:5173',
	'access-control-allow-credentials': 'true'
};

/** @param {object} value */
const base64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

const ACCESS = {
	receptionist: { role: 'receptionist', permissions: ['view_customers'], manageable_roles: [] },
	provider: { role: 'provider', permissions: [], manageable_roles: [] }
};

const FOLLOW_UP = {
	id: 'fu-1',
	source: 'call',
	reason: 'escalated',
	status: 'open',
	business_id: BUSINESS,
	customer_id: 'cust-1',
	booking_id: null,
	contact_name: 'Noura',
	contact_phone: '+966500000777',
	contact_email: null,
	summary: 'Wants a refund: the salon closed on her slot.',
	customer_message: 'أبي أسترجع فلوسي',
	opened_at: new Date(Date.now() - 20 * 60_000).toISOString(),
	resolved_at: null
};

/**
 * @param {import('@playwright/test').Page} page
 * @param {keyof typeof ACCESS} role
 * @returns {Promise<{ method: string, path: string }[]>} the API requests the page made
 */
async function signInAs(page, role) {
	const now = Math.floor(Date.now() / 1000);
	const token = [
		base64url({ alg: 'HS256', typ: 'JWT' }),
		base64url({ sub: 'user-1', kind: 'staff', tenants: [TENANT], iat: now, exp: now + 3600 }),
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
	/** @type {{ method: string, path: string }[]} */ const requests = [];
	let resolved = false;
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
		const url = new URL(request.url());
		const path = url.pathname.replace(/^.*\/api\/v1/, '');
		requests.push({ method: request.method(), path });
		if (path === `/tenants/${TENANT}/memberships/me`) {
			return route.fulfill({ headers: cors, json: ACCESS[role] });
		}
		if (path === '/auth/me') {
			return route.fulfill({
				headers: cors,
				json: { id: 'user-1', email: 'u@example.com', full_name: 'U', is_superuser: false }
			});
		}
		if (path === '/tenants') {
			return route.fulfill({
				headers: cors,
				json: { items: [{ id: TENANT, name_en: 'Follow-up Salon', name_ar: 'صالون' }] }
			});
		}
		if (path === `/tenants/${TENANT}/follow-ups/${FOLLOW_UP.id}/resolve`) {
			resolved = true;
			return route.fulfill({
				headers: cors,
				json: { ...FOLLOW_UP, status: 'resolved', resolved_at: new Date().toISOString() }
			});
		}
		if (path === `/tenants/${TENANT}/follow-ups`) {
			const open = url.searchParams.get('status') === 'open';
			const items = open === resolved ? [] : [{ ...FOLLOW_UP, status: open ? 'open' : 'resolved' }];
			return route.fulfill({ headers: cors, json: { items } });
		}
		return route.fulfill({ headers: cors, json: { items: [] } });
	});
	return requests;
}

test.use({ viewport: { width: 1280, height: 900 } });

test('a receptionist sees who to call back, why, and marks it resolved', async ({ page }) => {
	const requests = await signInAs(page, 'receptionist');
	await page.goto('/app/follow-ups');

	await expect(page.getByText('Noura')).toBeVisible();
	await expect(page.getByRole('link', { name: '+966500000777' })).toHaveAttribute(
		'href',
		'tel:+966500000777'
	);
	await expect(page.getByText('The assistant handed it to you')).toBeVisible();
	await expect(page.getByText('Wants a refund: the salon closed on her slot.')).toBeVisible();
	await expect(page.getByText('أبي أسترجع فلوسي')).toBeVisible();

	await page.getByRole('button', { name: 'Mark resolved' }).click();

	await expect(page.getByText('Nobody is waiting on you')).toBeVisible();
	expect(requests).toContainEqual({
		method: 'POST',
		path: `/tenants/${TENANT}/follow-ups/${FOLLOW_UP.id}/resolve`
	});

	await page.getByRole('tab', { name: 'Resolved' }).click();
	await expect(page.getByText('Noura')).toBeVisible();
	await expect(page.getByRole('button', { name: 'Mark resolved' })).toHaveCount(0);
});

test('a provider has no follow-ups link and is not shown any', async ({ page }) => {
	const requests = await signInAs(page, 'provider');
	await page.goto('/app/follow-ups');

	await expect(
		page.getByRole('navigation', { name: 'Dashboard' }).getByRole('link', { name: 'Follow-ups' })
	).toHaveCount(0);
	await expect(page.getByText('Noura')).toHaveCount(0);
	expect(requests.some(({ path }) => path.includes('/follow-ups'))).toBe(false);
});
