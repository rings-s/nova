import { expect, test } from '@playwright/test';

// "Use my location" on the discover page, with a scripted browser location:
// real browsers often answer first with a fast, rough guess (Wi-Fi or IP,
// kilometres out) and only then with a precise fix. The page has to follow
// the precise one, say how sure it is, and let the customer correct it.

const cors = { 'access-control-allow-origin': '*' };
const TRUE_SPOT = { lat: 24.7136, lng: 46.6753 }; // where the customer really is
const IP_GUESS = { lat: 24.9, lng: 46.5 }; // ~27 km away

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
		searches.push(new URL(route.request().url()));
		return route.fulfill({ headers: cors, json: { items: [] } });
	});
	return searches;
}

/** A controllable `navigator.geolocation`, driven through `window.__geo`. */
/** @param {import('@playwright/test').Page} page */
async function scriptGeolocation(page) {
	await page.addInitScript(() => {
		/** @type {{ ok: (p: unknown) => void }[]} */ const pending = [];
		/** @type {Map<number, { ok: (p: unknown) => void }>} */ const watchers = new Map();
		let nextId = 1;
		/** @param {number} latitude @param {number} longitude @param {number} accuracy */
		const position = (latitude, longitude, accuracy) => ({
			coords: { latitude, longitude, accuracy },
			timestamp: Date.now()
		});
		Object.defineProperty(navigator, 'geolocation', {
			configurable: true,
			value: {
				/** @param {(p: unknown) => void} ok */
				getCurrentPosition: (ok) => pending.push({ ok }),
				/** @param {(p: unknown) => void} ok */
				watchPosition: (ok) => {
					const id = nextId++;
					watchers.set(id, { ok });
					return id;
				},
				/** @param {number} id */
				clearWatch: (id) => watchers.delete(id)
			}
		});
		/** @type {any} */ (window).__geo = {
			/** The quick, first answer. @param {number} lat @param {number} lng @param {number} accuracy */
			answer: (lat, lng, accuracy) =>
				pending.splice(0).forEach((p) => p.ok(position(lat, lng, accuracy))),
			/** A later, watched fix. @param {number} lat @param {number} lng @param {number} accuracy */
			emit: (lat, lng, accuracy) =>
				[...watchers.values()].forEach((w) => w.ok(position(lat, lng, accuracy))),
			watching: () => watchers.size
		};
	});
}

/** @param {URL[]} searches */
const lastLocated = (searches) =>
	[...searches].reverse().find((url) => url.searchParams.get('latitude'));

/** @param {import('@playwright/test').Page} page */
async function useMyLocation(page) {
	await page.goto('/discover');
	await page.waitForLoadState('networkidle');
	await page.getByRole('button', { name: 'Use my location' }).first().click();
}

test.use({ viewport: { width: 1280, height: 900 } });

test('a rough first guess is replaced by the precise fix', async ({ page }) => {
	const searches = await stubApi(page);
	await scriptGeolocation(page);
	await useMyLocation(page);

	await page.evaluate(
		({ lat, lng }) => /** @type {any} */ (window).__geo.answer(lat, lng, 25_000),
		IP_GUESS
	);
	await expect(page.getByText(/could only place you within about 25 km/)).toBeVisible();

	await expect
		.poll(() => page.evaluate(() => /** @type {any} */ (window).__geo.watching()))
		.toBe(1);
	await page.evaluate(
		({ lat, lng }) => /** @type {any} */ (window).__geo.emit(lat, lng, 20),
		TRUE_SPOT
	);

	await expect(
		page.getByText('Showing salons near you — located to within about 20 m.')
	).toBeVisible();
	await expect
		.poll(() => Number(lastLocated(searches)?.searchParams.get('latitude')))
		.toBeCloseTo(TRUE_SPOT.lat, 4);
	expect(Number(lastLocated(searches)?.searchParams.get('longitude'))).toBeCloseTo(
		TRUE_SPOT.lng,
		4
	);
	// Precise enough: the page stopped listening instead of draining the battery.
	await expect
		.poll(() => page.evaluate(() => /** @type {any} */ (window).__geo.watching()))
		.toBe(0);
});

test('small wobbles in the fix do not re-run the search', async ({ page }) => {
	const searches = await stubApi(page);
	await scriptGeolocation(page);
	await useMyLocation(page);

	await page.evaluate(
		({ lat, lng }) => /** @type {any} */ (window).__geo.answer(lat, lng, 400),
		TRUE_SPOT
	);
	await expect(page.getByText(/located to within about 400 m/)).toBeVisible();
	await page.waitForLoadState('networkidle');
	const before = searches.filter((url) => url.searchParams.get('latitude')).length;

	// 30 m away, and surer: the circle tightens, the search stays put.
	await page.evaluate(
		({ lat, lng }) => /** @type {any} */ (window).__geo.emit(lat + 0.00027, lng, 150),
		TRUE_SPOT
	);
	await expect(page.getByText(/located to within about 150 m/)).toBeVisible();
	await page.waitForLoadState('networkidle');

	expect(searches.filter((url) => url.searchParams.get('latitude')).length).toBe(before);
});

test('the customer can drag the dot to correct a poor fix', async ({ page }) => {
	const searches = await stubApi(page);
	await scriptGeolocation(page);
	await useMyLocation(page);
	await page.evaluate(
		({ lat, lng }) => /** @type {any} */ (window).__geo.answer(lat, lng, 25_000),
		IP_GUESS
	);

	const dot = page.getByTitle('You are here — drag to correct');
	await expect(dot).toBeVisible();
	// The mouse can only drag what is on screen, and the map glides to the fix:
	// bring it into view, then grab the dot once it has stopped moving.
	await dot.scrollIntoViewIfNeeded();
	/** @type {{ x: number, y: number, width: number, height: number } | null} */
	let last = null;
	await expect
		.poll(async () => {
			const previous = last;
			last = await dot.boundingBox();
			return previous !== null && last !== null && previous.x === last.x && previous.y === last.y;
		})
		.toBe(true);
	const box = await dot.boundingBox();
	if (!box) throw new Error('The position dot is not on screen.');
	await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
	await page.mouse.down();
	await page.mouse.move(box.x + 120, box.y + 80, { steps: 8 });
	await page.mouse.up();

	await expect(page.getByText('Showing salons near the spot you placed on the map.')).toBeVisible();
	const placed = lastLocated(searches);
	expect(Number(placed?.searchParams.get('latitude'))).not.toBeCloseTo(IP_GUESS.lat, 3);

	// A late fix from the device does not undo the customer's correction.
	await page.evaluate(
		({ lat, lng }) => /** @type {any} */ (window).__geo.emit(lat, lng, 5_000),
		IP_GUESS
	);
	await expect(page.getByText('Showing salons near the spot you placed on the map.')).toBeVisible();
});
