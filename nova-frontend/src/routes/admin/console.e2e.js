import { expect, test } from '@playwright/test';

// The platform console against a stubbed API: who may open it, browsing a
// table into a row, running one of its curated actions, and editing, adding
// and deleting rows directly. The API enforces
// all of this itself (`require_superuser`); here we check the page follows.

const origin = 'http://localhost:5173';
// `/auth/*` is fetched with credentials, and a browser refuses a wildcard
// origin on a credentialed response, so echo the page's own.
const cors = { 'access-control-allow-origin': origin, 'access-control-allow-credentials': 'true' };

/** @param {object} value */
const base64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

const TABLES = [
	{ name: 'users', group: 'identity', estimated_rows: 2 },
	{ name: 'bookings', group: 'booking', estimated_rows: 40 },
	{ name: 'customer_business_first_bookings', group: 'billing', estimated_rows: 3 },
	{ name: 'admin_audit_log', group: 'platform', estimated_rows: 9 }
];

/** @param {string} name @param {Partial<import('$lib/api/admin.js').AdminColumn>} [extra] */
const column = (name, extra = {}) => ({
	name,
	type: 'text',
	nullable: false,
	primary_key: false,
	masked: false,
	searchable: true,
	filterable: true,
	references: null,
	choices: [],
	writable: true,
	required: false,
	max_length: null,
	...extra
});

const DEACTIVATE = {
	name: 'deactivate_user',
	label: 'Deactivate account',
	destructive: true,
	requires_reason: false
};

const USERS = {
	name: 'users',
	group: 'identity',
	editable: true,
	primary_key: ['id'],
	columns: [
		column('email', { required: true, max_length: 255 }),
		column('password_hash', { masked: true, searchable: false, filterable: false }),
		column('is_active', { type: 'boolean', searchable: false }),
		column('id', { type: 'uuid', primary_key: true, searchable: false })
	],
	actions: [DEACTIVATE],
	related: [{ table: 'memberships', column: 'user_id' }]
};

const USER_ID = '11111111-2222-3333-4444-555555555555';
/** @param {boolean} active @param {string} [email] */
const userRow = (active, email = 'stylist@example.com') => ({
	id: USER_ID,
	tenant_id: null,
	values: { id: USER_ID, email, password_hash: '••••••', is_active: active },
	actions: [DEACTIVATE]
});

/**
 * @param {import('@playwright/test').Page} page
 * @param {{ superuser: boolean }} account
 * @returns {Promise<string[]>} the API calls the page made, as `METHOD path?query`, with a
 *   JSON body after a space when there is one
 */
async function signIn(page, { superuser }) {
	const now = Math.floor(Date.now() / 1000);
	const token = [
		base64url({ alg: 'HS256', typ: 'JWT' }),
		base64url({ sub: 'admin-1', kind: 'customer', tenants: [], iat: now, exp: now + 3600 }),
		'signature'
	].join('.');
	await page.addInitScript((accessToken) => {
		localStorage.setItem('nova.auth.v1', JSON.stringify({ accessToken, refreshToken: 'r' }));
	}, token);

	/** @type {string[]} */ const calls = [];
	let active = true;
	let email = 'stylist@example.com';
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
		const body = request.postData();
		calls.push(`${request.method()} ${path}${url.search}${body ? ` ${body}` : ''}`);

		if (path === '/auth/me') {
			return route.fulfill({
				headers: cors,
				json: { id: 'admin-1', email: 'ops@nova.sa', is_superuser: superuser }
			});
		}
		if (path === '/admin/tables') return route.fulfill({ headers: cors, json: TABLES });
		if (path === '/admin/tables/users') return route.fulfill({ headers: cors, json: USERS });
		if (path === '/admin/tables/users/rows' && request.method() === 'POST') {
			const { values } = JSON.parse(body ?? '{}');
			return route.fulfill({ status: 201, headers: cors, json: userRow(true, values.email) });
		}
		if (path === '/admin/tables/users/rows') {
			const matchesFilter = url.searchParams.getAll('filter').every((filter) => {
				const [column, value] = filter.split(':');
				return column !== 'is_active' || String(active) === value;
			});
			return route.fulfill({
				headers: cors,
				json: {
					items: matchesFilter ? [userRow(active)] : [],
					total: matchesFilter ? 1 : 0,
					limit: 50,
					offset: 0
				}
			});
		}
		if (path === `/admin/tables/users/rows/${USER_ID}`) {
			if (request.method() === 'DELETE') return route.fulfill({ status: 204, headers: cors });
			if (request.method() === 'PATCH') email = JSON.parse(body ?? '{}').values.email ?? email;
			return route.fulfill({ headers: cors, json: userRow(active, email) });
		}
		if (path === `/admin/tables/users/rows/${USER_ID}/actions/deactivate_user`) {
			active = false;
			return route.fulfill({ headers: cors, json: userRow(active, email) });
		}
		if (path === '/admin/tables/bookings') {
			return route.fulfill({
				headers: cors,
				json: { ...USERS, name: 'bookings', group: 'booking', actions: [], related: [] }
			});
		}
		if (path === '/admin/tables/bookings/rows') {
			return route.fulfill({
				headers: cors,
				json: { items: [], total: 0, limit: 50, offset: 0 }
			});
		}
		return route.fulfill({ status: 404, headers: cors, json: { error: { code: 'not_found' } } });
	});
	return calls;
}

test('an account that is not a NOVA administrator is turned away', async ({ page }) => {
	const calls = await signIn(page, { superuser: false });
	await page.goto('/admin');

	await expect(page.getByText('Only NOVA administrators can open this page')).toBeVisible();
	expect(calls.some((call) => call.includes('/admin/tables'))).toBe(false);
});

test('a superuser browses a table into a row and deactivates it', async ({ page }) => {
	const calls = await signIn(page, { superuser: true });
	await page.setViewportSize({ width: 1280, height: 900 });
	await page.goto('/admin');

	await expect(page.getByRole('heading', { name: 'Every table' })).toBeVisible();
	await page
		.getByRole('complementary', { name: 'Tables' })
		.getByRole('link', { name: 'Users' })
		.click();

	await expect(page.getByRole('heading', { name: 'Users' })).toBeVisible();
	await expect(page.getByText('stylist@example.com')).toBeVisible();
	await page.getByRole('link', { name: '11111111…' }).click();

	// Every field, the secret one shown as hidden rather than empty.
	await expect(page.getByText('stylist@example.com')).toBeVisible();
	await expect(page.getByTitle('Hidden')).toBeVisible();
	await expect(page.getByRole('link', { name: /Memberships/ })).toHaveAttribute(
		'href',
		`/admin/tables/memberships?filter=user_id%3A${USER_ID}`
	);

	await page.getByRole('button', { name: 'Deactivate account' }).click();
	const dialog = page.getByRole('dialog');
	await expect(dialog).toBeVisible();
	await dialog.getByRole('button', { name: 'Deactivate account' }).click();

	await expect(page.getByText('Done: Deactivate account.')).toBeVisible();
	await expect(page.getByText('No', { exact: true })).toBeVisible();
	expect(calls).toContain(
		`POST /admin/tables/users/rows/${USER_ID}/actions/deactivate_user {"reason":null}`
	);
});

test('first-booking claims are listed under Billing in the admin console', async ({ page }) => {
	await signIn(page, { superuser: true });
	await page.setViewportSize({ width: 1280, height: 900 });
	await page.goto('/admin');

	const billing = page.getByRole('complementary', { name: 'Tables' });
	await expect(
		billing.getByRole('link', { name: 'Customer business first bookings' })
	).toBeVisible();
});

test('filters live in the URL, so a filtered view can be linked to', async ({ page }) => {
	const calls = await signIn(page, { superuser: true });
	await page.goto('/admin/tables/bookings?filter=customer_id:c-1&q=noura');

	await expect(page.getByText('No rows match')).toBeVisible();
	const listed = calls.find((call) => call.startsWith('GET /admin/tables/bookings/rows'));
	expect(listed).toContain('filter=customer_id%3Ac-1');
	expect(listed).toContain('q=noura');

	await page.getByRole('button', { name: 'Remove filter customer_id:c-1' }).click();
	await expect(page).toHaveURL(/\/admin\/tables\/bookings\?q=noura$/);
});

test('a filter added through the form is sent to the table rows API', async ({ page }) => {
	const calls = await signIn(page, { superuser: true });
	await page.goto('/admin/tables/users');

	await expect(page.getByText('stylist@example.com')).toBeVisible();
	await page.getByLabel('Filter by').selectOption('is_active');
	await expect(page.getByRole('button', { name: 'Add filter' })).toBeDisabled();
	await page.getByLabel('Equals').selectOption('true');
	await page.getByRole('button', { name: 'Add filter' }).click();

	await expect(page.getByRole('button', { name: 'Remove filter is_active:true' })).toBeVisible();
	await expect
		.poll(() =>
			calls.find(
				(call) =>
					call.startsWith('GET /admin/tables/users/rows') &&
					call.includes('filter=is_active%3Atrue')
			)
		)
		.toBeTruthy();
	await expect(page.getByText('stylist@example.com')).toBeVisible();
	await expect(page).toHaveURL(/filter=is_active%3Atrue/);
});

test('a superuser edits a row, sending only what changed, then deletes it', async ({ page }) => {
	const calls = await signIn(page, { superuser: true });
	await page.setViewportSize({ width: 1280, height: 900 });
	await page.goto(`/admin/tables/users/${USER_ID}`);

	await page.getByRole('button', { name: 'Edit fields' }).click();
	// The primary key isn't editable, and the secret starts blank.
	await expect(page.getByLabel('id', { exact: true })).toHaveCount(0);
	await expect(page.getByLabel('password_hash')).toHaveValue('');
	await page.getByLabel('email').fill('renamed@example.com');
	await page.getByRole('button', { name: 'Save changes' }).click();

	await expect(page.getByText('Saved.')).toBeVisible();
	await expect(page.getByText('renamed@example.com')).toBeVisible();
	expect(calls).toContain(
		`PATCH /admin/tables/users/rows/${USER_ID} {"values":{"email":"renamed@example.com"}}`
	);

	await page.getByRole('button', { name: 'Delete row' }).click();
	await page.getByRole('dialog').getByRole('button', { name: 'Delete row' }).click();
	await expect(page).toHaveURL(/\/admin\/tables\/users$/);
	expect(calls).toContain(`DELETE /admin/tables/users/rows/${USER_ID}`);
});

test('a superuser adds a row; blank fields are left to their defaults', async ({ page }) => {
	const calls = await signIn(page, { superuser: true });
	await page.goto('/admin/tables/users');

	await page.getByRole('link', { name: 'Add row' }).click();
	await expect(page.getByRole('heading', { name: 'Add row' })).toBeVisible();
	await page.getByLabel('email').fill('new@example.com');
	await page.getByRole('button', { name: 'Add row' }).click();

	await expect(page).toHaveURL(new RegExp(`/admin/tables/users/${USER_ID}$`));
	expect(calls).toContain('POST /admin/tables/users/rows {"values":{"email":"new@example.com"}}');
});
