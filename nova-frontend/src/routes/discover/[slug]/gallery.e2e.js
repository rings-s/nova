import { expect, test } from '@playwright/test';

// A storefront's photos against a stubbed API: the mosaic, and the full-screen
// viewer with its keyboard controls.

const cors = { 'access-control-allow-origin': '*' };
const SLUG = 'photo-salon';
/** A 1×1 WebP, standing in for every photo. */
const PIXEL = Buffer.from('UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAwA0JaQAA3AA/vuUAAA=', 'base64');

/** @param {string} id @param {'cover'|'gallery'} kind */
const photo = (id, kind) => ({
	id,
	kind,
	width: 1600,
	height: 1067,
	urls: {
		large: `/api/v1/discovery/photos/${id}/large`,
		thumb: `/api/v1/discovery/photos/${id}/thumb`
	}
});

/** @param {import('@playwright/test').Page} page */
async function stubApi(page) {
	await page.route('**/api/v1/discovery/photos/**', (route) =>
		route.fulfill({ contentType: 'image/webp', headers: cors, body: PIXEL })
	);
	await page.route(`**/api/v1/discovery/businesses/${SLUG}`, (route) =>
		route.fulfill({
			headers: cors,
			json: {
				business_id: 'biz-1',
				tenant_id: 'tenant-1',
				slug: SLUG,
				name_en: 'Photo Salon',
				name_ar: 'صالون الصور',
				description_en: null,
				description_ar: null,
				rating_count: 0,
				rating_average: null,
				photos: [
					photo('p-cover', 'cover'),
					photo('p-1', 'gallery'),
					photo('p-2', 'gallery'),
					photo('p-3', 'gallery')
				],
				locations: [],
				services: [],
				providers: []
			}
		})
	);
	await page.route('**/api/v1/discovery/businesses/*/referrals', (route) =>
		route.fulfill({ headers: cors, json: { referral_token: 't', expires_at: '2099-01-01' } })
	);
}

test.use({ viewport: { width: 1280, height: 900 } });

test('the storefront shows its photos and opens them full screen', async ({ page }) => {
	await stubApi(page);
	await page.goto(`/discover/${SLUG}`);

	await expect(page.getByRole('img', { name: 'Photo Salon' })).toBeVisible();
	const showAll = page.getByRole('button', { name: 'Show all 4 photos' });
	await showAll.click();

	const viewer = page.getByRole('dialog', { name: 'Photo Salon photos' });
	await expect(viewer).toBeVisible();
	await expect(viewer.getByText('1 / 4')).toBeVisible();

	await page.keyboard.press('ArrowRight');
	await expect(viewer.getByText('2 / 4')).toBeVisible();
	await page.keyboard.press('ArrowLeft');
	await page.keyboard.press('ArrowLeft');
	await expect(viewer.getByText('4 / 4')).toBeVisible(); // wraps around

	await page.keyboard.press('Escape');
	await expect(viewer).toHaveCount(0);
	await expect(showAll).toBeFocused(); // focus returns to what opened it
});
