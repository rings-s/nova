import { expect, test } from '@playwright/test';

const origin = 'http://localhost:5173';
const cors = { 'access-control-allow-origin': origin, 'access-control-allow-credentials': 'true' };
const CATEGORY_ID = '11111111-2222-3333-4444-555555555555';

/** @param {object} value */
const base64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

test('a superuser can list, create, rename, retire, and restore service categories', async ({
	page
}) => {
	const now = Math.floor(Date.now() / 1000);
	const token = [
		base64url({ alg: 'HS256', typ: 'JWT' }),
		base64url({ sub: 'admin-1', kind: 'customer', tenants: [], iat: now, exp: now + 3600 }),
		'signature'
	].join('.');
	await page.addInitScript((accessToken) => {
		localStorage.setItem('nova.auth.v1', JSON.stringify({ accessToken, refreshToken: 'r' }));
	}, token);

	/** @type {Array<{ method: string, path: string, body?: unknown }>} */
	const calls = [];
	/** @type {{ id: string, slug: string, name_en: string, name_ar: string, is_active: boolean, created_at: string, updated_at: string }[]} */
	const categories = [
		{
			id: CATEGORY_ID,
			slug: 'spa',
			name_en: 'Spa',
			name_ar: 'السبا',
			is_active: true,
			created_at: '2026-01-01T00:00:00Z',
			updated_at: '2026-01-01T00:00:00Z'
		}
	];

	await page.route('**/api/v1/**', async (route) => {
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
		const method = request.method();
		const body = request.postDataJSON();
		calls.push({ method, path, ...(body ? { body } : {}) });

		if (path === '/auth/me') {
			return route.fulfill({
				headers: cors,
				json: { id: 'admin-1', email: 'ops@nova.sa', is_superuser: true }
			});
		}
		if (path === '/admin/tables') return route.fulfill({ headers: cors, json: [] });
		if (path === '/admin/catalog/categories' && method === 'GET') {
			return route.fulfill({ headers: cors, json: categories });
		}
		if (path === '/admin/catalog/categories' && method === 'POST') {
			const created = {
				id: CATEGORY_ID.replace(/.$/, '6'),
				slug: 'nail-art',
				...body,
				is_active: true,
				created_at: '2026-01-01T00:00:00Z',
				updated_at: '2026-01-01T00:00:00Z'
			};
			categories.push(/** @type {typeof categories[number]} */ (created));
			return route.fulfill({ status: 201, headers: cors, json: created });
		}
		if (path.startsWith('/admin/catalog/categories/') && method === 'PATCH') {
			const id = path.split('/').at(-1);
			const category = categories.find((item) => item.id === id);
			if (!category) return route.fulfill({ status: 404, headers: cors });
			Object.assign(category, body, { updated_at: new Date().toISOString() });
			return route.fulfill({ headers: cors, json: category });
		}
		return route.fulfill({ status: 404, headers: cors, json: { error: { code: 'not_found' } } });
	});

	await page.goto('/admin/categories');
	await expect(page.getByRole('heading', { name: 'Service categories', level: 1 })).toBeVisible();
	await expect(page.locator('li').filter({ hasText: 'Spa' })).toContainText('السبا');
	expect(calls).toContainEqual({ method: 'GET', path: '/admin/catalog/categories' });

	await page.getByLabel('Name (English)').fill('Nail Art');
	await page.getByLabel('Name (Arabic)').fill('فن الأظافر');
	await page.getByRole('button', { name: 'Add category' }).click();

	const createdRow = page.locator('li').filter({ hasText: 'nail-art' });
	await expect(createdRow).toContainText('فن الأظافر');
	expect(calls).toContainEqual({
		method: 'POST',
		path: '/admin/catalog/categories',
		body: { name_en: 'Nail Art', name_ar: 'فن الأظافر' }
	});

	await createdRow.getByRole('button', { name: 'Rename' }).click();
	const editForm = page.locator('li form');
	await editForm.getByLabel('Name (English)').fill('Nails');
	await editForm.getByLabel('Name (Arabic)').fill('الأظافر');
	await editForm.getByRole('button', { name: 'Save' }).click();
	const renamedRow = page.locator('li').filter({ hasText: 'Nails' });
	await expect(renamedRow).toContainText('Nails');
	expect(calls).toContainEqual({
		method: 'PATCH',
		path: `/admin/catalog/categories/${CATEGORY_ID.replace(/.$/, '6')}`,
		body: { name_en: 'Nails', name_ar: 'الأظافر' }
	});

	await renamedRow.getByRole('button', { name: 'Retire' }).click();
	await expect(renamedRow.getByText('Retired')).toBeVisible();
	expect(calls).toContainEqual({
		method: 'PATCH',
		path: `/admin/catalog/categories/${CATEGORY_ID.replace(/.$/, '6')}`,
		body: { is_active: false }
	});

	await renamedRow.getByRole('button', { name: 'Restore' }).click();
	await expect(renamedRow.getByText('Retired')).toHaveCount(0);
	expect(calls).toContainEqual({
		method: 'PATCH',
		path: `/admin/catalog/categories/${CATEGORY_ID.replace(/.$/, '6')}`,
		body: { is_active: true }
	});
});
