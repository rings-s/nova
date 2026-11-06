import { expect, test } from '@playwright/test';

// The discover page against a stubbed API, so the map is exercised without a
// backend or a seeded database. The fixtures have the shape the real endpoints
// return (`nova_backend/app/modules/discovery/schemas.py`).

/** A flat grey square, standing in for every OpenStreetMap tile. */
const BLANK_TILE =
	'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#e5e7eb"/></svg>';

const cors = { 'access-control-allow-origin': '*' };

/** @param {string} id @param {string} name @param {number} lat @param {number} lng */
function listing(id, name, lat, lng) {
	return {
		business_id: `biz-${id}`,
		tenant_id: 'tenant-1',
		slug: `salon-${id}`,
		name_en: name,
		name_ar: 'صالون',
		description_en: null,
		description_ar: null,
		location_id: id,
		location_name_en: 'Main Branch',
		location_name_ar: 'الفرع الرئيسي',
		city: 'Riyadh',
		latitude: lat,
		longitude: lng,
		timezone: 'Asia/Riyadh',
		starting_price: '150.00',
		currency: 'SAR',
		distance_km: null
	};
}

const HOSTILE = '<img src=x onerror="window.__pwned = true">';

const LISTINGS = [
	listing('a', 'Glow Studio', 24.7136, 46.6753),
	listing('b', 'Olaya Spa', 24.69, 46.68),
	listing('c', 'Red Sea Salon', 21.4858, 39.1925),
	// A name is whatever the business typed. It must never be parsed as markup.
	listing('d', HOSTILE, 24.72, 46.7)
];

/**
 * @param {import('@playwright/test').Page} page
 * @returns {Promise<{ maps: URL[], lists: URL[] }>} the requests the page makes, as they arrive
 */
async function stubApi(page) {
	/** @type {URL[]} */ const maps = [];
	/** @type {URL[]} */ const lists = [];

	await page.route('https://tile.openstreetmap.org/**', (route) =>
		route.fulfill({ contentType: 'image/svg+xml', body: BLANK_TILE })
	);
	await page.route('**/api/v1/discovery/categories', (route) =>
		route.fulfill({
			headers: cors,
			json: [
				{
					id: 'beauty-clinics-id',
					slug: 'beauty-clinics',
					name_en: 'Beauty clinics',
					name_ar: 'عيادات التجميل'
				},
				{ id: 'spa-id', slug: 'spa', name_en: 'Spa', name_ar: 'السبا' }
			]
		})
	);
	await page.route('**/api/v1/discovery/map**', (route) => {
		maps.push(new URL(route.request().url()));
		return route.fulfill({
			contentType: 'application/geo+json',
			headers: cors,
			json: {
				type: 'FeatureCollection',
				truncated: false,
				features: LISTINGS.map((properties) => ({
					type: 'Feature',
					id: properties.location_id,
					geometry: { type: 'Point', coordinates: [properties.longitude, properties.latitude] },
					properties
				}))
			}
		});
	});
	await page.route('**/api/v1/discovery/businesses?**', (route) => {
		lists.push(new URL(route.request().url()));
		return route.fulfill({ headers: cors, json: { items: LISTINGS } });
	});

	return { maps, lists };
}

test.describe('on a wide screen', () => {
	test.use({ viewport: { width: 1280, height: 900 } });

	test('every listing is a pin, and a pin opens its Quick View', async ({ page }) => {
		await stubApi(page);
		await page.goto('/discover');
		// The map is a view of the results at every width, not a panel beside them.
		await expect(
			page.getByRole('region', { name: 'Map of spas, salons and clinics' })
		).toBeHidden();
		const pins = page.locator('.leaflet-marker-icon');
		await expect(pins).toHaveCount(LISTINGS.length);
		await page.getByRole('button', { name: 'Map', exact: true }).click();

		// Jeddah's pin, because the Riyadh ones stack on each other at country zoom.
		await page.getByTitle('Red Sea Salon — Main Branch').click();
		// Only the Quick View modal has this link; the name itself is also on the card.
		await expect(page.getByRole('link', { name: 'View Full Menu' })).toBeVisible();
	});

	test('where to search comes from the device or the map, not a city list', async ({ page }) => {
		const { lists } = await stubApi(page);
		await page.goto('/discover');

		const form = page.getByRole('search');
		await expect(form.getByRole('button', { name: 'Use my location' })).toBeVisible();
		await expect(form.getByRole('combobox')).toHaveCount(0);
		await expect.poll(() => lists.length).toBeGreaterThan(0);
		expect(lists.every((url) => !url.searchParams.has('city'))).toBe(true);
	});

	test('beauty clinic and spa filters use the platform category slugs', async ({ page }) => {
		const { maps, lists } = await stubApi(page);
		await page.goto('/discover');

		await page.getByRole('button', { name: 'Beauty clinics' }).click();
		await expect.poll(() => lists.at(-1)?.searchParams.get('category')).toBe('beauty-clinics');
		await expect.poll(() => maps.at(-1)?.searchParams.get('category')).toBe('beauty-clinics');

		await page.getByRole('button', { name: 'Spa', exact: true }).click();
		await expect.poll(() => lists.at(-1)?.searchParams.get('category')).toBe('spa');
		await expect.poll(() => maps.at(-1)?.searchParams.get('category')).toBe('spa');
	});

	test('pagination detects the end when the result count is an exact multiple of a page', async ({
		page
	}) => {
		const { lists } = await stubApi(page);
		const venues = Array.from({ length: 24 }, (_, index) =>
			listing(String(index), `Venue ${index}`, 24.7136, 46.6753)
		);
		await page.route('**/api/v1/discovery/businesses?**', (route) => {
			const url = new URL(route.request().url());
			const requestLimit = Number(url.searchParams.get('limit'));
			if (requestLimit !== 13) {
				return route.fulfill({ headers: cors, json: { items: LISTINGS } });
			}
			lists.push(url);
			const offset = Number(url.searchParams.get('offset'));
			return route.fulfill({
				headers: cors,
				json: { items: venues.slice(offset, offset + requestLimit) }
			});
		});

		await page.goto('/discover');
		const pagination = page.getByRole('navigation', { name: 'Pagination' });
		await expect.poll(() => lists.at(-1)?.searchParams.get('limit')).toBe('13');
		await expect(page.getByRole('heading', { name: 'Venue 0' })).toBeVisible();
		await pagination.getByRole('button', { name: 'Next' }).click();

		await expect.poll(() => lists.at(-1)?.searchParams.get('offset')).toBe('12');
		await expect(page.getByRole('heading', { name: 'Venue 12' })).toBeVisible();
		await expect(pagination.getByRole('button', { name: 'Next' })).toBeDisabled();
		await expect(pagination.getByRole('button', { name: 'Previous' })).toBeEnabled();
	});

	test("a price sort is the server's, and starts again at page one", async ({ page }) => {
		const { lists } = await stubApi(page);
		await page.route('**/api/v1/discovery/businesses?**', (route) => {
			const url = new URL(route.request().url());
			lists.push(url);
			// Always a full page and one more, so there is always a next page.
			const items = Array.from({ length: 13 }, (_, index) =>
				listing(`${url.searchParams.get('offset')}-${index}`, `Venue ${index}`, 24.7, 46.7)
			);
			return route.fulfill({ headers: cors, json: { items } });
		});

		await page.goto('/discover');
		const pagination = page.getByRole('navigation', { name: 'Pagination' });
		await pagination.getByRole('button', { name: 'Next' }).click();
		await expect.poll(() => lists.at(-1)?.searchParams.get('offset')).toBe('12');
		await expect(pagination.getByText('Page 2')).toBeVisible();

		await page.getByLabel('Sort by').selectOption('price-low');
		await expect.poll(() => lists.at(-1)?.searchParams.get('sort')).toBe('price_asc');
		expect(lists.at(-1)?.searchParams.get('offset')).toBe('0');

		await pagination.getByRole('button', { name: 'Next' }).click();
		await expect.poll(() => lists.at(-1)?.searchParams.get('offset')).toBe('12');
		expect(lists.at(-1)?.searchParams.get('sort')).toBe('price_asc');
	});

	test('a new search term starts again at page one, once typing pauses', async ({ page }) => {
		const { lists } = await stubApi(page);
		await page.route('**/api/v1/discovery/businesses?**', (route) => {
			const url = new URL(route.request().url());
			lists.push(url);
			const items = Array.from({ length: 13 }, (_, index) =>
				listing(`${url.searchParams.get('offset')}-${index}`, `Venue ${index}`, 24.7, 46.7)
			);
			return route.fulfill({ headers: cors, json: { items } });
		});

		await page.goto('/discover');
		await page
			.getByRole('navigation', { name: 'Pagination' })
			.getByRole('button', { name: 'Next' })
			.click();
		await expect.poll(() => lists.at(-1)?.searchParams.get('offset')).toBe('12');

		const before = lists.length;
		await page.getByRole('searchbox', { name: 'Search venues or services' }).fill('massage');
		await expect.poll(() => lists.at(-1)?.searchParams.get('q')).toBe('massage');
		expect(lists.at(-1)?.searchParams.get('offset')).toBe('0');
		// One search for the whole word, not one per keystroke.
		expect(lists.length - before).toBe(1);
	});

	test('a business name is shown as text, never parsed as markup', async ({ page }) => {
		await stubApi(page);
		await page.goto('/discover');
		await expect(page.locator('.leaflet-marker-icon')).toHaveCount(LISTINGS.length);

		// If the name had been treated as HTML the broken image would have fired
		// its handler by now.
		expect(await page.evaluate(() => /** @type {any} */ (window).__pwned)).toBeUndefined();
		await expect(page.getByTitle(`${HOSTILE} — Main Branch`)).toHaveCount(1);
	});

	test('"Search this area" narrows both the list and the map to the viewport', async ({ page }) => {
		const { maps, lists } = await stubApi(page);
		await page.goto('/discover');
		await expect(page.locator('.leaflet-marker-icon')).toHaveCount(LISTINGS.length);
		await page.getByRole('button', { name: 'Map', exact: true }).click();
		expect(maps.at(-1)?.searchParams.has('bbox')).toBe(false);

		await page.getByRole('button', { name: 'Search this area' }).click();
		await expect(page.getByRole('button', { name: 'Clear area' })).toBeVisible();

		await expect.poll(() => maps.at(-1)?.searchParams.get('bbox')).not.toBeNull();
		const bbox = /** @type {string} */ (maps.at(-1)?.searchParams.get('bbox'));
		const [west, south, east, north] = bbox.split(',').map(Number);
		// The order the API expects, and a sane box: what Leaflet's bounds would
		// give if the world were shown twice is clamped before it is sent.
		expect(west).toBeLessThan(east);
		expect(south).toBeLessThan(north);
		expect(Math.min(west, east)).toBeGreaterThanOrEqual(-180);
		expect(Math.max(west, east)).toBeLessThanOrEqual(180);
		expect(Math.min(south, north)).toBeGreaterThanOrEqual(-90);
		expect(Math.max(south, north)).toBeLessThanOrEqual(90);
		await expect.poll(() => lists.at(-1)?.searchParams.get('bbox')).toBe(bbox);

		await page.getByRole('button', { name: 'Clear area' }).click();
		await expect(page.getByRole('button', { name: 'Search this area' })).toBeVisible();
		await expect.poll(() => maps.at(-1)?.searchParams.has('bbox')).toBe(false);
		await expect.poll(() => lists.at(-1)?.searchParams.has('bbox')).toBe(false);
	});
});

test.describe('on a phone', () => {
	test.use({ viewport: { width: 390, height: 844 } });

	test('the map is behind a toggle, and is fitted to its pins once shown', async ({ page }) => {
		await stubApi(page);
		await page.goto('/discover');

		await expect(
			page.getByRole('region', { name: 'Map of spas, salons and clinics' })
		).toBeHidden();
		// The pins exist (hidden) only once the page's script runs; a toggle
		// clicked before that lands on server-rendered HTML and does nothing.
		await expect(page.locator('.leaflet-marker-icon')).toHaveCount(LISTINGS.length);
		await page.getByRole('button', { name: 'Map', exact: true }).click();

		const region = page.getByRole('region', { name: 'Map of spas, salons and clinics' });
		await expect(region).toBeVisible();
		const pins = page.locator('.leaflet-marker-icon');
		await expect(pins).toHaveCount(LISTINGS.length);

		// The map was created while hidden. If it had been fitted at zero size,
		// the pins would sit outside the frame once it was shown.
		// Measured together, inside the frame's own coordinates: the page scrolls
		// the map into view when it is shown, and two separate measurements
		// could straddle that scroll.
		const outside = () =>
			region.evaluate((frame) => {
				const box = frame.getBoundingClientRect();
				return [...document.querySelectorAll('.leaflet-marker-icon')]
					.map((pin) => pin.getBoundingClientRect())
					.filter(
						(at) =>
							at.left < box.left ||
							at.right > box.right ||
							at.top < box.top ||
							at.bottom > box.bottom
					).length;
			});
		// Polled: Leaflet animates the fit, and a pin can be mid-glide.
		await expect.poll(outside).toBe(0);
	});

	test('the map does not paint over the Quick View modal', async ({ page }) => {
		await stubApi(page);
		await page.goto('/discover');
		await expect(page.locator('.leaflet-marker-icon')).toHaveCount(LISTINGS.length);
		await page.getByRole('button', { name: 'Map', exact: true }).click();
		await expect(page.locator('.leaflet-marker-icon')).toHaveCount(LISTINGS.length);
		await page.getByTitle('Red Sea Salon — Main Branch').click();
		await expect(page.getByRole('link', { name: 'View Full Menu' })).toBeVisible();

		// Leaflet gives its controls a z-index of 1000, far above the modal's. They
		// stay under it only because the map is its own stacking context. So find
		// the zoom control and ask what is on top at that very spot: it has to be
		// the modal's backdrop, not the control.
		//
		// On a phone, because from `lg` up the map sits in a `position: sticky`
		// wrapper, which is a stacking context whether or not the map is one, so
		// only this layout can notice the map losing its own.
		const zoomIn = page.locator('.leaflet-control-zoom-in');
		const box = /** @type {NonNullable<Awaited<ReturnType<typeof zoomIn.boundingBox>>>} */ (
			await zoomIn.boundingBox()
		);
		const topmostIsMap = await page.evaluate(
			([x, y]) => document.elementFromPoint(x, y)?.closest('.leaflet-container') != null,
			[box.x + box.width / 2, box.y + box.height / 2]
		);
		expect(topmostIsMap).toBe(false);
	});
});
