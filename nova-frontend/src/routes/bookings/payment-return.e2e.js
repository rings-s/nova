import { expect, test } from '@playwright/test';

// Back from Moyasar's checkout. The page asks the API to check the payment
// with Moyasar (`POST …/payments/{id}/sync`) and reports what it found; it
// never trusts the redirect itself.

const TENANT = 'tenant-pay';
const PAYMENT = 'payment-1';
const cors = { 'access-control-allow-origin': '*' };

/** @param {object} value */
const base64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

/**
 * @param {import('@playwright/test').Page} page
 * @param {string} status what the sync reports
 * @returns {Promise<string[]>} the API paths the page called
 */
async function returnFromCheckout(page, status) {
	const now = Math.floor(Date.now() / 1000);
	const token = [
		base64url({ alg: 'HS256', typ: 'JWT' }),
		base64url({ sub: 'user-1', kind: 'customer', iat: now, exp: now + 3600 }),
		'signature'
	].join('.');
	await page.addInitScript((accessToken) => {
		localStorage.setItem('nova.auth.v1', JSON.stringify({ accessToken, refreshToken: 'r' }));
	}, token);

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
		if (path === `/tenants/${TENANT}/payments/${PAYMENT}/sync`) {
			return route.fulfill({
				headers: cors,
				json: {
					id: PAYMENT,
					booking_id: 'booking-1',
					amount: '150.00',
					currency: 'SAR',
					status,
					gateway: 'moyasar',
					gateway_payment_id: status === 'captured' ? 'pay_1' : null,
					webhook_verified: false,
					refunded_amount: '0.00',
					failure_code: status === 'failed' ? 'checkout_expired' : null,
					captured_at: null,
					created_at: new Date().toISOString()
				}
			});
		}
		return route.fulfill({ headers: cors, json: { items: [], total: 0 } });
	});

	await page.goto(`/bookings?tenant=${TENANT}&payment=${PAYMENT}`);
	return calls;
}

test('a paid checkout is confirmed by the server, and the address is cleaned', async ({ page }) => {
	const calls = await returnFromCheckout(page, 'captured');

	await expect(page.getByText('Payment received. Your booking is confirmed.')).toBeVisible();
	await expect(page).toHaveURL(/\/bookings$/);
	expect(calls.filter((c) => c.endsWith('/sync'))).toEqual([
		`POST /tenants/${TENANT}/payments/${PAYMENT}/sync`
	]);
});

test('an unpaid return says the booking is held, and claims nothing', async ({ page }) => {
	await returnFromCheckout(page, 'pending');

	await expect(page.getByText("We haven't received your payment yet.")).toBeVisible();
	await expect(page.getByText('Payment received.')).toHaveCount(0);
});

test('a failed checkout says nothing was charged', async ({ page }) => {
	await returnFromCheckout(page, 'failed');

	await expect(page.getByText('nothing was charged')).toBeVisible();
});
