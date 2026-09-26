import { expect, test } from '@playwright/test';

// The app in Arabic: chosen by a cookie or the browser's language, rendered
// by the server already right-to-left, switchable from the header, and with
// the backend's errors read from their stable codes.

// As the real API answers: `/auth/*` is fetched with credentials (the refresh
// cookie), and a browser refuses a credentialed response to a wildcard origin.
const cors = {
	'access-control-allow-origin': new URL(process.env.E2E_BASE_URL ?? 'http://localhost:5173')
		.origin,
	'access-control-allow-credentials': 'true'
};

test('the server renders Arabic right-to-left when the cookie asks for it', async ({
	context,
	page
}) => {
	await context.addCookies([{ name: 'nova_locale', value: 'ar', url: 'http://localhost:5173' }]);
	const response = await page.request.get('/', { headers: { cookie: 'nova_locale=ar' } });
	const html = await response.text();
	expect(html).toContain('<html lang="ar" dir="rtl">');

	await page.goto('/');
	await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
	await expect(page.getByRole('heading', { level: 1 })).toContainText('كل ما يحتاجه صالونك.');
	await expect(page).toHaveTitle(/الحجوزات وقوائم الانتظار/);
});

test('a browser that prefers Arabic gets Arabic without choosing', async ({ browser }) => {
	const context = await browser.newContext({ locale: 'ar-SA' });
	const page = await context.newPage();
	await page.goto('/pricing');
	await expect(page.locator('html')).toHaveAttribute('lang', 'ar');
	await expect(page.getByRole('heading', { level: 1 })).toContainText('اختر الباقة التي تناسب');
	await context.close();
});

test('English is the default, and the switch changes language and direction, and remembers', async ({
	page
}) => {
	await page.setViewportSize({ width: 1280, height: 900 });
	await page.goto('/');
	await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
	await expect(page.getByRole('link', { name: 'Pricing' }).first()).toBeVisible();

	// Retried: a click that lands before the page has hydrated does nothing.
	await expect(async () => {
		await page.getByRole('button', { name: /Switch language to العربية/ }).click();
		await expect(page.locator('html')).toHaveAttribute('dir', 'rtl', { timeout: 1000 });
	}).toPass();
	await expect(page.getByRole('link', { name: 'الأسعار' }).first()).toBeVisible();

	// Remembered: a fresh load is rendered in Arabic by the server.
	await page.reload();
	await expect(page.locator('html')).toHaveAttribute('lang', 'ar');
	await expect(page.getByRole('link', { name: 'الأسعار' }).first()).toBeVisible();

	await expect(async () => {
		await page.getByRole('button', { name: /English/ }).click();
		await expect(page.locator('html')).toHaveAttribute('dir', 'ltr', { timeout: 1000 });
	}).toPass();
});

test('a backend error reads in Arabic from its code, not its English message', async ({
	context,
	page
}) => {
	await context.addCookies([{ name: 'nova_locale', value: 'ar', url: 'http://localhost:5173' }]);
	await page.route('**/api/v1/auth/login', (route) =>
		route.fulfill({
			status: 401,
			headers: cors,
			json: {
				error: {
					code: 'invalid_credentials',
					message: 'Invalid email or password.',
					field: null,
					retryable: false
				}
			}
		})
	);
	await page.goto('/login');
	await page.getByLabel('البريد الإلكتروني').fill('someone@example.com');
	await page.getByLabel('كلمة المرور').fill('not-the-password');
	await page.getByRole('button', { name: 'تسجيل الدخول' }).last().click();

	await expect(page.getByText('البريد الإلكتروني أو كلمة المرور غير صحيحة.')).toBeVisible();
	await expect(page.getByText('Invalid email or password.')).toHaveCount(0);
});
