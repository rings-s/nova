import { expect, test } from '@playwright/test';

// Plans are what a business pays NOVA, so a signed-in customer never sees
// the pricing page: no link to it, and opening it by URL lands on /discover.
// Everyone else, signed out or staff, still has it.

/** @param {object} value */
const base64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

/**
 * @param {import('@playwright/test').Page} page
 * @param {'customer' | 'staff'} kind
 */
async function signInAs(page, kind) {
	const now = Math.floor(Date.now() / 1000);
	const token = [
		base64url({ alg: 'HS256', typ: 'JWT' }),
		base64url({ sub: 'user-1', kind, tenants: [], roles: [], iat: now, exp: now + 3600 }),
		'signature'
	].join('.');
	await page.addInitScript((accessToken) => {
		localStorage.setItem('nova.auth.v1', JSON.stringify({ accessToken, refreshToken: 'r' }));
	}, token);
}

test.use({ viewport: { width: 1280, height: 900 } });

test('a customer has no pricing link, and the page sends them to discover', async ({ page }) => {
	await signInAs(page, 'customer');
	await page.goto('/about');
	await expect(page.getByRole('link', { name: 'My bookings' }).first()).toBeVisible();
	await expect(page.getByRole('link', { name: 'Pricing' })).toHaveCount(0);

	await page.goto('/pricing');
	await expect(page).toHaveURL(/\/discover$/);
});

test('signed out, pricing is still linked and open', async ({ page }) => {
	await page.goto('/about');
	await expect(
		page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Pricing' })
	).toBeVisible();
	await page.goto('/pricing');
	await expect(page).toHaveURL(/\/pricing$/);
});
