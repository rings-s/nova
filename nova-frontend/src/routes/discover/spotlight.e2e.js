import { expect, test } from '@playwright/test';

// "Near you" and "Top rated" on the discover page, against a stubbed API. The
// fixtures have the shape `ListingCardOut` returns, ratings included
// (`nova_backend/app/modules/discovery/schemas.py`).

const cors = { 'access-control-allow-origin': '*' };
const RIYADH = { latitude: 24.7136, longitude: 46.6753 };

/**
 * @param {string} id @param {string} name
 * @param {{ business?: string, count?: number, average?: number|null, km?: number|null }} [extra]
 */
function listing(id, name, { business = id, count = 0, average = null, km = null } = {}) {
	return {
		business_id: `biz-${business}`,
		tenant_id: 'tenant-1',
		slug: `salon-${id}`,
		name_en: name,
		name_ar: 'صالون',
		description_en: null,
		description_ar: null,
		location_id: `loc-${id}`,
		location_name_en: 'Main Branch',
		location_name_ar: 'الفرع الرئيسي',
		city: 'Riyadh',
		latitude: 24.7,
		longitude: 46.7,
		timezone: 'Asia/Riyadh',
		starting_price: '150.00',
		currency: 'SAR',
		distance_km: km,
		rating_count: count,
		rating_average: average
	};
}

// What `sort=rating` answers: best score first, and a chain's second branch
// and an unrated salon mixed in, as the real endpoint can return them.
const BY_RATING = [
	listing('proven', 'Proven Spa', { count: 200, average: 4.8 }),
	listing('proven-2', 'Proven Spa', { business: 'proven', count: 200, average: 4.8 }),
	listing('lucky', 'Lucky Salon', { count: 1, average: 5 }),
	listing('new', 'Brand New Salon')
];
const NEARBY = [
	listing('close', 'Corner Salon', { km: 0.8, count: 12, average: 4.5 }),
	listing('far', 'Across Town Spa', { km: 7.3 })
];

/** @param {import('@playwright/test').Page} page @returns {Promise<URL[]>} */
async function stubApi(page) {
	/** @type {URL[]} */ const searches = [];
	await page.route('https://tile.openstreetmap.org/**', (route) =>
		route.fulfill({
			contentType: 'image/svg+xml',
			body: '<svg xmlns="http://www.w3.org/2000/svg"/>'
		})
	);
	await page.route('**/api/v1/discovery/map**', (route) =>
		route.fulfill({
			headers: cors,
			json: { type: 'FeatureCollection', truncated: false, features: [] }
		})
	);
	await page.route('**/api/v1/discovery/businesses?**', (route) => {
		const url = new URL(route.request().url());
		searches.push(url);
		const sort = url.searchParams.get('sort');
		const items = sort === 'rating' ? BY_RATING : sort === 'distance' ? NEARBY : BY_RATING;
		return route.fulfill({ headers: cors, json: { items } });
	});
	return searches;
}

/**
 * Waits until the page is hydrated. A click on server-rendered HTML before
 * then does nothing, and on a busy machine that window is seconds long. The
 * Top rated row is filled by a client-side fetch, so seeing it proves the
 * page's script is running.
 * @param {import('@playwright/test').Page} page
 */
async function hydrated(page) {
	await expect(
		page.getByRole('region', { name: 'Top rated' }).getByRole('link').first()
	).toBeVisible({ timeout: 20_000 });
}

test.use({ viewport: { width: 1280, height: 900 } });

test('top rated shows rated salons once each, in the order the API ranked them', async ({
	page
}) => {
	const searches = await stubApi(page);
	await page.goto('/discover');

	await hydrated(page);
	const top = page.getByRole('region', { name: 'Top rated' });
	await expect(top.getByRole('link')).toHaveText([/Proven Spa/, /Lucky Salon/]);
	// A single 5-star visit is shown as exactly that, not as "5 stars".
	await expect(top.getByRole('img', { name: /Rated 5\.0 out of 5 from 1 rating/ })).toBeVisible();
	expect(searches.some((url) => url.searchParams.get('sort') === 'rating')).toBe(true);
});

test.describe('with the device location shared', () => {
	test.use({ geolocation: RIYADH, permissions: ['geolocation'] });

	test('near you asks first, then lists the closest salons with their distance', async ({
		page
	}) => {
		const searches = await stubApi(page);
		await page.goto('/discover');

		await hydrated(page);
		const near = page.getByRole('region', { name: 'Near you' });
		// Nothing is asked of the browser until the customer chooses to share.
		await expect(near.getByText(/Share your location/)).toBeVisible();
		await near.getByRole('button', { name: 'Use my location' }).click();

		await expect(near.getByRole('link')).toHaveText([/Corner Salon/, /Across Town Spa/]);
		await expect(near.getByText('0.8 km')).toBeVisible();

		const located = searches.find((url) => url.searchParams.get('sort') === 'distance');
		expect(Number(located?.searchParams.get('latitude'))).toBeCloseTo(RIYADH.latitude, 3);
		expect(Number(located?.searchParams.get('longitude'))).toBeCloseTo(RIYADH.longitude, 3);
	});

	test('"Nearest to me" re-sorts the full results by distance', async ({ page }) => {
		const searches = await stubApi(page);
		await page.goto('/discover');
		await hydrated(page);

		await page.getByLabel('Sort by').selectOption('nearest');

		await expect
			.poll(() => searches.some((url) => url.searchParams.get('sort') === 'distance'))
			.toBe(true);
		await expect(page.getByLabel('Sort by')).toHaveValue('nearest');
	});
});

test.describe('with location blocked', () => {
	test.use({ permissions: [] });

	test('near you explains what happened instead of failing silently', async ({ page }) => {
		await stubApi(page);
		await page.addInitScript(() => {
			/** @type {any} */ (navigator.geolocation).getCurrentPosition = (
				/** @type {any} */ _ok,
				/** @type {(e: object) => void} */ fail
			) => fail({ code: 1, message: 'User denied Geolocation' });
		});
		await page.goto('/discover');
		await hydrated(page);

		await page
			.getByRole('region', { name: 'Near you' })
			.getByRole('button', { name: 'Use my location' })
			.click();

		await expect(page.getByText(/Location is blocked for this site/)).toBeVisible();
		await expect(page.getByLabel('Sort by')).toHaveValue('recommended');
	});
});
