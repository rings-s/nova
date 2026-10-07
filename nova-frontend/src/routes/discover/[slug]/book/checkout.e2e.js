import { expect, test } from '@playwright/test';

// Paying a deposit on the booking page, against a stubbed API: the intent's
// `checkout` mounts Moyasar's Payment Form in the page, bound to the invoice
// the server opened. Nothing reaches Moyasar before the payer submits.

const SLUG = 'pay-salon';
const TENANT = 'tenant-pay';
const SERVICE = 'svc-1';
const INVOICE = '6b1f0a2e-3c4d-4e5f-8a9b-0c1d2e3f4a5b';

/** @param {object} value */
const base64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

/** @param {import('@playwright/test').Request} request */
function cors(request) {
	// `/auth/*` is fetched with credentials, which refuses a wildcard origin.
	return {
		'access-control-allow-origin': request.headers().origin ?? 'http://localhost:5173',
		'access-control-allow-credentials': 'true',
		'access-control-allow-headers': '*',
		'access-control-allow-methods': '*'
	};
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {{ checkout: object|null, redirect_url: string|null }} intent
 * @returns {Promise<{ intents: object[] }>}
 */
async function stubApi(page, intent) {
	const now = Math.floor(Date.now() / 1000);
	const token = [
		base64url({ alg: 'HS256', typ: 'JWT' }),
		base64url({ sub: 'user-1', kind: 'customer', iat: now, exp: now + 3600 }),
		'signature'
	].join('.');
	await page.addInitScript((accessToken) => {
		localStorage.setItem('nova.auth.v1', JSON.stringify({ accessToken, refreshToken: 'r' }));
	}, token);

	const startsAt = new Date(Date.now() + 2 * 24 * 3600 * 1000);
	startsAt.setUTCHours(9, 0, 0, 0);
	const endsAt = new Date(startsAt.getTime() + 3600 * 1000);
	const booking = {
		id: 'booking-1',
		tenant_id: TENANT,
		service_id: SERVICE,
		starts_at: startsAt.toISOString(),
		ends_at: endsAt.toISOString(),
		price: '150.00',
		currency: 'SAR',
		status: 'pending_payment'
	};

	/** @type {object[]} */ const intents = [];
	await page.route('**/api/v1/**', async (route) => {
		const request = route.request();
		const headers = cors(request);
		if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
		const path = new URL(request.url()).pathname.replace(/^.*\/api\/v1/, '');

		if (path === `/discovery/businesses/${SLUG}`) {
			return route.fulfill({
				headers,
				json: {
					business_id: 'biz-1',
					tenant_id: TENANT,
					slug: SLUG,
					name_en: 'Pay Salon',
					name_ar: 'صالون الدفع',
					description_en: null,
					description_ar: null,
					rating_count: 0,
					rating_average: null,
					photos: [],
					locations: [],
					services: [
						{
							id: SERVICE,
							name_en: 'Haircut',
							name_ar: 'قص شعر',
							duration_minutes: 60,
							price: '150.00',
							currency: 'SAR'
						}
					],
					providers: []
				}
			});
		}
		if (path.endsWith('/availability')) {
			return route.fulfill({
				headers,
				json: {
					business_id: 'biz-1',
					tenant_id: TENANT,
					slots: [
						{
							slot_id: 'slot-1',
							provider_id: 'prov-1',
							provider_name_en: 'Nora',
							provider_name_ar: 'نورة',
							location_id: 'loc-1',
							service_id: SERVICE,
							starts_at: booking.starts_at,
							ends_at: booking.ends_at
						}
					]
				}
			});
		}
		if (path === `/tenants/${TENANT}/bookings` && request.method() === 'POST') {
			return route.fulfill({ status: 201, headers, json: booking });
		}
		if (path === `/tenants/${TENANT}/payments/intents`) {
			intents.push(request.postDataJSON());
			return route.fulfill({
				status: 201,
				headers,
				json: {
					payment: {
						id: 'payment-1',
						booking_id: booking.id,
						amount: '150.00',
						currency: 'SAR',
						status: 'pending',
						gateway: 'moyasar',
						gateway_payment_id: null,
						webhook_verified: false,
						refunded_amount: '0.00',
						failure_code: null,
						captured_at: null,
						created_at: new Date().toISOString()
					},
					...intent
				}
			});
		}
		return route.fulfill({ headers, json: { items: [], total: 0 } });
	});
	return { intents };
}

/** @param {import('@playwright/test').Page} page */
async function bookAndPay(page) {
	await page.goto(`/discover/${SLUG}/book?service=${SERVICE}`);
	await page.getByRole('button', { name: /Earliest:/ }).click();
	await page.getByRole('dialog').getByRole('button', { name: /Nora/ }).click();
	await page.getByRole('button', { name: 'Confirm booking' }).first().click();
	await page.getByRole('button', { name: 'Pay deposit' }).click();
}

test.use({ viewport: { width: 1280, height: 900 } });

test('the deposit is paid in Moyasar’s form, on the invoice the server opened', async ({
	page
}) => {
	/** @type {string[]} */ const moyasarCalls = [];
	page.on('request', (request) => {
		if (new URL(request.url()).hostname.endsWith('moyasar.com')) moyasarCalls.push(request.url());
	});
	const { intents } = await stubApi(page, {
		checkout: {
			publishable_api_key: 'pk_test_e2e',
			invoice_id: INVOICE,
			amount: 15000,
			currency: 'SAR',
			description: 'NOVA booking BOOKING1',
			callback_url: `http://localhost:5173/bookings?tenant=${TENANT}&payment=payment-1`
		},
		redirect_url: 'https://checkout.moyasar.com/should-not-be-used'
	});

	await bookAndPay(page);

	// A customer names neither amount nor currency: the server decides both.
	expect(intents).toHaveLength(1);
	expect(intents[0]).toMatchObject({ booking_id: 'booking-1', amount: null, currency: null });
	await expect(page.getByText('Deposit due now')).toBeVisible();
	const form = page.locator('.moyasar-form');
	await expect(form.locator('input').first()).toBeVisible();
	await expect(page.getByText('Secured by Moyasar')).toBeVisible();
	// Still on NOVA: the hosted page is only the fallback.
	await expect(page).toHaveURL(new RegExp(`/discover/${SLUG}/book`));
	expect(moyasarCalls).toEqual([]);
});

test('without a publishable key, the payer goes to Moyasar’s hosted page', async ({ page }) => {
	await stubApi(page, { checkout: null, redirect_url: 'https://checkout.moyasar.com/inv_1' });
	await page.route('https://checkout.moyasar.com/**', (route) =>
		route.fulfill({ contentType: 'text/html', body: '<h1>Moyasar checkout</h1>' })
	);

	await bookAndPay(page);

	await expect(page).toHaveURL('https://checkout.moyasar.com/inv_1');
});
