import { expect, test } from '@playwright/test';
import { parseCoordinates } from '../../../lib/map/coordinates.js';
import { cityCenter } from '../../../lib/map/cities.js';

// The catalog's location flows against a stubbed API: an owner puts a branch on
// the map when adding it, and sets, moves or removes the pin on one that exists.
// The stubs answer the way `nova_backend/app/modules/catalog/router.py` does.

const TENANT = 'tenant-1';
const BUSINESS = 'biz-1';
const RIYADH = { lat: 24.7136, lng: 46.6753 };
const JEDDAH = { lat: 21.4858, lng: 39.1925 };

const cors = { 'access-control-allow-origin': '*' };
const preflight = {
	...cors,
	'access-control-allow-methods': 'GET, POST, PATCH, PUT, DELETE, OPTIONS',
	// `Authorization` has to be named; a wildcard does not cover it.
	'access-control-allow-headers': 'authorization, content-type, x-correlation-id, idempotency-key'
};

const BLANK_TILE =
	'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#e5e7eb"/></svg>';

/** @param {object} value */
const base64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

/** @param {string} id @param {string} name @param {{lat:number,lng:number}|null} at */
function branch(id, name, at) {
	return {
		id,
		tenant_id: TENANT,
		business_id: BUSINESS,
		name_en: name,
		name_ar: 'فرع',
		slug: id,
		timezone: 'Asia/Riyadh',
		city: 'Riyadh',
		latitude: at?.lat ?? null,
		longitude: at?.lng ?? null,
		is_active: true,
		created_at: '2026-09-01T00:00:00Z',
		updated_at: '2026-09-01T00:00:00Z'
	};
}

/**
 * Signs in as staff of one tenant with one business, and stubs the API. Returns
 * what the page sent, and the tiles it asked OpenStreetMap for.
 * @param {import('@playwright/test').Page} page
 * @param {ReturnType<typeof branch>[]} [existing]
 */
async function signInAndStub(page, existing = []) {
	const now = Math.floor(Date.now() / 1000);
	const token = [
		base64url({ alg: 'HS256', typ: 'JWT' }),
		base64url({
			sub: 'user-1',
			kind: 'staff',
			tenants: [TENANT],
			roles: ['owner'],
			iat: now,
			exp: now + 3600
		}),
		'signature'
	].join('.');
	await page.addInitScript(
		([accessToken, tenant, business]) => {
			localStorage.setItem('nova.auth.v1', JSON.stringify({ accessToken, refreshToken: 'r' }));
			localStorage.setItem('nova.activeTenantId', tenant);
			localStorage.setItem('nova.businessByTenant', JSON.stringify({ [tenant]: business }));
		},
		[token, TENANT, BUSINESS]
	);

	const state = {
		locations: [...existing],
		/** @type {any[]} */ created: [],
		/** @type {any[]} */ positioned: [],
		/** @type {string[]} */ tiles: [],
		/** @type {{ latitude: number, longitude: number }[]} */ looked: [],
		/** What the map service answers: a place, `null` for nowhere, or a status to fail with. */
		/** @type {(lat: number) => object | number} */
		place: (lat) =>
			lat > 23
				? {
						name_en: 'Al Olaya branch',
						name_ar: 'فرع العليا',
						city_en: 'Riyadh',
						city_ar: 'الرياض'
					}
				: {
						name_en: 'Al Andalus branch',
						name_ar: 'فرع الأندلس',
						city_en: 'Jeddah',
						city_ar: 'جدة'
					}
	};

	await page.route('https://tile.openstreetmap.org/**', (route) => {
		state.tiles.push(new URL(route.request().url()).pathname);
		return route.fulfill({ contentType: 'image/svg+xml', body: BLANK_TILE });
	});

	await page.route('**/api/v1/**', (route) => {
		const request = route.request();
		const method = request.method();
		/** @param {unknown} json @param {number} [status] */
		const respond = (json, status = 200) => route.fulfill({ status, headers: cors, json });

		if (method === 'OPTIONS') return route.fulfill({ status: 204, headers: preflight });

		const path = new URL(request.url()).pathname.replace(/^.*\/api\/v1/, '');
		const catalog = `/tenants/${TENANT}/catalog`;

		// The caller's role in this business, which decides what the dashboard
		// shows: an owner, as the token above says.
		if (method === 'GET' && path === `/tenants/${TENANT}/memberships/me`) {
			return respond({
				role: 'owner',
				permissions: [
					'manage_catalog',
					'manage_subscription',
					'refund_payments',
					'view_analytics',
					'view_financials'
				],
				manageable_roles: ['manager', 'owner', 'provider', 'receptionist']
			});
		}
		if (method === 'GET' && path === `${catalog}/places/reverse`) {
			const query = new URL(request.url()).searchParams;
			const latitude = Number(query.get('latitude'));
			const longitude = Number(query.get('longitude'));
			state.looked.push({ latitude, longitude });
			const answer = state.place(latitude);
			if (typeof answer === 'number') {
				return respond(
					{ error: { code: 'geocoding_unavailable', message: 'Not answering.', retryable: true } },
					answer
				);
			}
			return respond({
				latitude,
				longitude,
				city_en: null,
				city_ar: null,
				district_en: null,
				district_ar: null,
				name_en: null,
				name_ar: null,
				...answer
			});
		}
		if (method === 'GET' && path === `${catalog}/businesses/${BUSINESS}/locations`) {
			return respond({ items: state.locations });
		}
		if (method === 'POST' && path === `${catalog}/locations`) {
			const body = request.postDataJSON();
			state.created.push(body);
			const created = {
				...branch(`loc-new-${state.created.length}`, body.name_en, null),
				name_ar: body.name_ar,
				city: body.city,
				latitude: body.latitude,
				longitude: body.longitude
			};
			state.locations.push(created);
			return respond(created, 201);
		}
		const position = path.match(new RegExp(`^${catalog}/locations/([^/]+)/position$`));
		if (method === 'PATCH' && position) {
			const body = request.postDataJSON();
			state.positioned.push({ id: position[1], ...body });
			const found = state.locations.find((l) => l.id === position[1]);
			if (!found) return respond({ error: { code: 'location_not_found' } }, 404);
			found.latitude = body.latitude;
			found.longitude = body.longitude;
			return respond(found);
		}
		return respond({ items: [] });
	});

	return state;
}

/** @param {import('@playwright/test').Page} page */
async function openAddLocation(page) {
	await page.goto('/app/catalog');
	await page.getByRole('button', { name: 'Add location' }).first().click();
	const dialog = page.getByRole('dialog', { name: 'Add location' });
	await expect(dialog).toBeVisible();
	return {
		dialog,
		submit: dialog.getByRole('button', { name: 'Add location' }),
		pins: dialog.locator('.leaflet-marker-icon'),
		nameEn: dialog.getByLabel('Name (English)'),
		nameAr: dialog.getByLabel('Name (Arabic)'),
		city: dialog.getByLabel('City')
	};
}

test.describe('adding a location', () => {
	test.use({ viewport: { width: 1280, height: 900 } });

	test('"Detect my location" fills the pin, the names and the city: nothing is typed', async ({
		page,
		context
	}) => {
		await context.grantPermissions(['geolocation']);
		await context.setGeolocation({ latitude: JEDDAH.lat, longitude: JEDDAH.lng });
		const state = await signInAndStub(page);
		const { dialog, submit, pins, nameEn, nameAr, city } = await openAddLocation(page);
		await expect(submit).toBeDisabled();

		await dialog.getByRole('button', { name: 'Detect my location' }).click();

		await expect(pins).toHaveCount(1);
		await expect(nameEn).toHaveValue('Al Andalus branch');
		await expect(nameAr).toHaveValue('فرع الأندلس');
		await expect(city).toHaveValue('Jeddah');
		// Read-only: filled in from the map, never typed.
		for (const field of [nameEn, nameAr, city]) await expect(field).toHaveAttribute('readonly');
		await expect(dialog.getByLabel('Coordinates', { exact: true })).toHaveCount(0);
		expect(state.looked.at(-1)).toEqual({ latitude: JEDDAH.lat, longitude: JEDDAH.lng });

		await submit.click();
		await expect.poll(() => state.created.length).toBe(1);
		expect(state.created[0]).toMatchObject({
			name_en: 'Al Andalus branch',
			name_ar: 'فرع الأندلس',
			city: 'Jeddah',
			latitude: JEDDAH.lat,
			longitude: JEDDAH.lng
		});
		await expect(page.getByText('On the map', { exact: true })).toBeVisible();
	});

	test('clicking the map places the pin and fills the form', async ({ page }) => {
		const state = await signInAndStub(page);
		const { dialog, submit, pins, nameEn, city } = await openAddLocation(page);

		await dialog.locator('.leaflet-container').click();

		await expect(pins).toHaveCount(1);
		await expect(nameEn).toHaveValue('Al Olaya branch');
		await expect(city).toHaveValue('Riyadh');
		await expect(submit).toBeEnabled();
		expect(state.looked).toHaveLength(1);
	});

	test('dragging the pin fills the form again from where it lands', async ({ page }) => {
		const state = await signInAndStub(page);
		const { dialog, pins, nameEn } = await openAddLocation(page);
		await dialog.locator('.leaflet-container').click();
		await expect(nameEn).toHaveValue('Al Olaya branch');
		state.place = () => ({
			name_en: 'As Salamah branch',
			name_ar: 'فرع السلامة',
			city_en: 'Riyadh',
			city_ar: 'الرياض'
		});

		const box = /** @type {NonNullable<Awaited<ReturnType<typeof pins.boundingBox>>>} */ (
			await pins.boundingBox()
		);
		const x = box.x + box.width / 2;
		const y = box.y + box.height / 2;
		await page.mouse.move(x, y);
		await page.mouse.down();
		await page.mouse.move(x + 60, y - 30, { steps: 8 });
		await page.mouse.up();

		await expect(nameEn).toHaveValue('As Salamah branch');
		expect(state.looked.length).toBeGreaterThanOrEqual(2);
	});

	test('where the map has no address, the add button waits for a better pin', async ({ page }) => {
		const state = await signInAndStub(page);
		state.place = () => ({});
		const { dialog, submit } = await openAddLocation(page);

		await dialog.locator('.leaflet-container').click();

		await expect(dialog.getByText('The map has no address here.')).toBeVisible();
		await expect(submit).toBeDisabled();
	});

	test('a map service that does not answer can be asked again', async ({ page }) => {
		const state = await signInAndStub(page);
		state.place = () => 503;
		const { dialog, submit, nameEn } = await openAddLocation(page);
		await dialog.locator('.leaflet-container').click();
		await expect(dialog.getByRole('button', { name: 'Try again' })).toBeVisible();
		await expect(submit).toBeDisabled();

		state.place = () => ({
			name_en: 'Al Olaya branch',
			name_ar: 'فرع العليا',
			city_en: 'Riyadh',
			city_ar: 'الرياض'
		});
		await dialog.getByRole('button', { name: 'Try again' }).click();

		await expect(nameEn).toHaveValue('Al Olaya branch');
		await expect(submit).toBeEnabled();
	});

	test('"Remove pin" empties the form, and the add button waits', async ({ page }) => {
		await signInAndStub(page);
		const { dialog, submit, pins, nameEn } = await openAddLocation(page);
		await dialog.locator('.leaflet-container').click();
		await expect(nameEn).toHaveValue('Al Olaya branch');

		await dialog.getByRole('button', { name: 'Remove pin' }).click();

		await expect(pins).toHaveCount(0);
		await expect(nameEn).toHaveCount(0);
		await expect(dialog.getByRole('button', { name: 'Detect my location' })).toBeVisible();
		await expect(submit).toBeDisabled();
	});
});

test.describe('positioning a branch that exists', () => {
	test.use({ viewport: { width: 1280, height: 900 } });

	test('sets, moves and removes the pin, and the card follows each step', async ({
		page,
		context
	}) => {
		await context.grantPermissions(['geolocation']);
		await context.setGeolocation({ latitude: RIYADH.lat, longitude: RIYADH.lng });
		const state = await signInAndStub(page, [
			branch('loc-a', 'Olaya Branch', null),
			branch('loc-b', 'Jeddah Branch', JEDDAH)
		]);
		await page.goto('/app/catalog');
		await expect(page.getByText('Not on the map yet')).toHaveCount(1);
		await expect(page.getByText('On the map', { exact: true })).toHaveCount(1);
		await expect(page.getByRole('link', { name: /View on OpenStreetMap/ }).first()).toHaveAttribute(
			'href',
			/mlat=21\.485800&mlon=39\.192500/
		);

		// Set: the branch that has none.
		await page.getByRole('button', { name: 'Set on map' }).click();
		const dialog = page.getByRole('dialog', { name: 'Map position' });
		await expect(dialog.getByText('Olaya Branch')).toBeVisible();
		await dialog.getByRole('button', { name: 'Detect my location' }).click();
		await expect(dialog.locator('.leaflet-marker-icon')).toHaveCount(1);
		await dialog.getByRole('button', { name: 'Save position' }).click();
		await expect.poll(() => state.positioned.length).toBe(1);
		expect(state.positioned[0]).toEqual({
			id: 'loc-a',
			latitude: RIYADH.lat,
			longitude: RIYADH.lng
		});
		await expect(page.getByText('On the map', { exact: true })).toHaveCount(2);
		await expect(page.getByText('Not on the map yet')).toHaveCount(0);

		// Move: the dialog opens on the pin it already has.
		await page.getByRole('button', { name: 'Move pin' }).first().click();
		const shown = dialog.locator('[data-coordinates]');
		await expect(shown).toHaveText('24.713600, 46.675300');
		// Moved by clicking elsewhere on the map: still nothing typed.
		await dialog.locator('.leaflet-container').click({ position: { x: 320, y: 70 } });
		await expect(shown).not.toHaveText('24.713600, 46.675300');
		const [lat, lng] = String(await shown.textContent())
			.split(',')
			.map(Number);
		await dialog.getByRole('button', { name: 'Save position' }).click();
		await expect.poll(() => state.positioned.length).toBe(2);
		expect(state.positioned[1]).toEqual({ id: 'loc-a', latitude: lat, longitude: lng });

		// Remove: both null, the pair the API accepts for "no pin".
		await page.getByRole('button', { name: 'Move pin' }).first().click();
		await dialog.getByRole('button', { name: 'Remove pin' }).click();
		await dialog.getByRole('button', { name: 'Save position' }).click();
		await expect.poll(() => state.positioned.length).toBe(3);
		expect(state.positioned[2]).toEqual({ id: 'loc-a', latitude: null, longitude: null });
		await expect(page.getByText('Not on the map yet')).toHaveCount(1);
	});
});

test.describe('reading coordinates', () => {
	test('accepts what an owner would paste, in either separator', () => {
		expect(parseCoordinates('24.7136, 46.6753')).toEqual({
			status: 'ok',
			latitude: 24.7136,
			longitude: 46.6753
		});
		expect(parseCoordinates('24.7136 46.6753')).toMatchObject({ status: 'ok' });
		expect(parseCoordinates('  -33.86;151.2  ')).toMatchObject({
			status: 'ok',
			latitude: -33.86,
			longitude: 151.2
		});
	});

	test('nothing at all means no pin, not an error', () => {
		expect(parseCoordinates('')).toEqual({ status: 'empty' });
		expect(parseCoordinates('   ')).toEqual({ status: 'empty' });
	});

	for (const text of [
		'24.7',
		'24.7, 46.6, 12',
		'north, east',
		'24.7136° N, 46.6753° E',
		'NaN, 46',
		'Infinity, 46',
		'1e2, 46',
		'0x10, 46'
	]) {
		test(`refuses "${text}" as not two plain numbers`, () => {
			expect(parseCoordinates(text).status).toBe('invalid');
		});
	}

	test('refuses what the API would', () => {
		expect(parseCoordinates('91, 46')).toMatchObject({ status: 'invalid' });
		expect(parseCoordinates('-91, 46')).toMatchObject({ status: 'invalid' });
		expect(parseCoordinates('24, 181')).toMatchObject({ status: 'invalid' });
		expect(parseCoordinates('24, -181')).toMatchObject({ status: 'invalid' });
		expect(parseCoordinates('90, 180')).toMatchObject({ status: 'ok' });
		expect(parseCoordinates('-90, -180')).toMatchObject({ status: 'ok' });
	});
});

test.describe('finding a city', () => {
	test('matches whole names in English and Arabic, ignoring case and spacing', () => {
		expect(cityCenter('Riyadh')).toEqual([24.7136, 46.6753]);
		expect(cityCenter('  riyadh ')).toEqual([24.7136, 46.6753]);
		expect(cityCenter('الرياض')).toEqual([24.7136, 46.6753]);
		expect(cityCenter('AL   Khobar')).toEqual(cityCenter('khobar'));
	});

	test('does not guess from a prefix, so typing "Ri" moves nothing', () => {
		expect(cityCenter('Ri')).toBeNull();
		expect(cityCenter('Riyadh City')).toBeNull();
		expect(cityCenter('')).toBeNull();
		expect(cityCenter(null)).toBeNull();
	});
});

// --- finding the device ------------------------------------------------------

/**
 * Replaces the browser's geolocation with one the test drives by hand, so every
 * path (a fix, a better fix, each failure) happens exactly when the test says.
 * @param {import('@playwright/test').Page} page
 */
async function scriptGeolocation(page) {
	await page.addInitScript(() => {
		/** @typedef {{ ok: (p: unknown) => void, err: (e: unknown) => void }} Callbacks */
		/** @type {Callbacks[]} */
		const pending = [];
		/** @type {Map<number, Callbacks>} */
		const watchers = new Map();
		let nextId = 1;
		/** @param {number} latitude @param {number} longitude @param {number} accuracy */
		const position = (latitude, longitude, accuracy) => ({
			coords: { latitude, longitude, accuracy },
			timestamp: Date.now()
		});
		/** @param {number} code @param {string} message */
		const error = (code, message) => ({ code, message });

		Object.defineProperty(navigator, 'geolocation', {
			configurable: true,
			value: {
				/** @param {Callbacks['ok']} ok @param {Callbacks['err']} err */
				getCurrentPosition: (ok, err) => {
					pending.push({ ok, err });
				},
				/** @param {Callbacks['ok']} ok @param {Callbacks['err']} err */
				watchPosition: (ok, err) => {
					const id = nextId++;
					watchers.set(id, { ok, err });
					return id;
				},
				/** @param {number} id */
				clearWatch: (id) => {
					watchers.delete(id);
				}
			}
		});

		/** @type {any} */ (window).__geo = {
			/** @param {number} lat @param {number} lng @param {number} accuracy */
			answer: (lat, lng, accuracy) =>
				pending.splice(0).forEach((p) => p.ok(position(lat, lng, accuracy))),
			/** @param {number} code @param {string} message */
			refuse: (code, message) => pending.splice(0).forEach((p) => p.err(error(code, message))),
			/** @param {number} lat @param {number} lng @param {number} accuracy */
			emit: (lat, lng, accuracy) =>
				[...watchers.values()].forEach((w) => w.ok(position(lat, lng, accuracy))),
			/** @param {number} code @param {string} message */
			failWatch: (code, message) =>
				[...watchers.values()].forEach((w) => w.err(error(code, message))),
			asked: () => pending.length,
			watching: () => watchers.size
		};
	});
}

/** @param {import('@playwright/test').Page} page */
function geoDriver(page) {
	/** @param {string} method @param {unknown[]} args */
	const call = (method, args) =>
		page.evaluate(
			([m, a]) => /** @type {any} */ (window).__geo[/** @type {string} */ (m)](...a),
			[method, args]
		);
	return {
		/** @param {number} lat @param {number} lng @param {number} accuracy */
		answer: (lat, lng, accuracy) => call('answer', [lat, lng, accuracy]),
		/** @param {number} code @param {string} message */
		refuse: (code, message) => call('refuse', [code, message]),
		/** @param {number} lat @param {number} lng @param {number} accuracy */
		emit: (lat, lng, accuracy) => call('emit', [lat, lng, accuracy]),
		/** @param {number} code @param {string} message */
		failWatch: (code, message) => call('failWatch', [code, message]),
		/** @returns {Promise<number>} */
		asked: () => call('asked', []),
		/** @returns {Promise<number>} */
		watching: () => call('watching', [])
	};
}

test.describe('finding the device', () => {
	test.use({ viewport: { width: 1280, height: 900 } });

	/** The accuracy circle is the only path Leaflet draws in the overlay pane. */
	const circle = (/** @type {import('@playwright/test').Locator} */ dialog) =>
		dialog.locator('.leaflet-overlay-pane path');

	test('a precise fix places the pin, shows how sure it is, and ends the search', async ({
		page
	}) => {
		await scriptGeolocation(page);
		await signInAndStub(page);
		const geo = geoDriver(page);
		const { dialog, pins } = await openAddLocation(page);
		const coordinates = dialog.locator('[data-coordinates]');
		const status = dialog.getByRole('status');

		await dialog.getByRole('button', { name: 'Detect my location' }).click();
		await expect(status).toContainText('Finding your location');
		await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeVisible();

		await geo.answer(RIYADH.lat, RIYADH.lng, 12);

		await expect(coordinates).toHaveText('24.713600, 46.675300');
		await expect(pins).toHaveCount(1);
		await expect(status).toContainText('within about 12 m');
		await expect(circle(dialog)).toHaveCount(1);
		await expect(dialog.getByRole('button', { name: 'Detect again' })).toBeEnabled();
		expect(await geo.watching()).toBe(0); // good enough: it did not go on looking
	});

	test('a rough fix moves the map but places no pin, and a better one then does', async ({
		page
	}) => {
		await scriptGeolocation(page);
		await signInAndStub(page);
		const geo = geoDriver(page);
		const { dialog, pins } = await openAddLocation(page);
		const coordinates = dialog.locator('[data-coordinates]');
		const status = dialog.getByRole('status');

		await dialog.getByRole('button', { name: 'Detect my location' }).click();
		await geo.answer(24.7, 46.7, 20_000);

		// 20 km is a different neighbourhood. Say so, and do not guess.
		await expect(status).toContainText('too rough for a pin');
		await expect(status).toContainText('within about 20 km');
		await expect(pins).toHaveCount(0);
		await expect(coordinates).toHaveCount(0);
		await expect(circle(dialog)).toHaveCount(1);
		await expect(status).toContainText('Refining');
		await expect.poll(() => geo.watching()).toBe(1);

		await geo.emit(RIYADH.lat, RIYADH.lng, 15);

		await expect(pins).toHaveCount(1);
		await expect(coordinates).toHaveText('24.713600, 46.675300');
		await expect(status).toContainText('within about 15 m');
		await expect(status).not.toContainText('Refining');
		expect(await geo.watching()).toBe(0);
	});

	test('a fix that arrives after the owner took over never moves their pin', async ({ page }) => {
		await scriptGeolocation(page);
		await signInAndStub(page);
		const geo = geoDriver(page);
		const { dialog, pins } = await openAddLocation(page);
		const coordinates = dialog.locator('[data-coordinates]');

		await dialog.getByRole('button', { name: 'Detect my location' }).click();
		await geo.answer(24.7, 46.7, 20_000);
		await expect.poll(() => geo.watching()).toBe(1);

		await dialog.locator('.leaflet-container').click(); // the owner picks the spot
		await expect(pins).toHaveCount(1);
		const chosen = String(await coordinates.textContent());
		await expect(circle(dialog)).toHaveCount(0);
		expect(await geo.watching()).toBe(0); // and the search was called off

		await geo.emit(21.4858, 39.1925, 5); // a late, precise fix from somewhere else

		await expect(coordinates).toHaveText(chosen);
		await expect(pins).toHaveCount(1);
	});

	test('cancelling stops the search and a late answer changes nothing', async ({ page }) => {
		await scriptGeolocation(page);
		await signInAndStub(page);
		const geo = geoDriver(page);
		const { dialog, pins } = await openAddLocation(page);
		const coordinates = dialog.locator('[data-coordinates]');

		await dialog.getByRole('button', { name: 'Detect my location' }).click();
		await dialog.getByRole('button', { name: 'Cancel' }).click();

		await expect(dialog.getByRole('status')).toHaveCount(0);
		await expect(dialog.getByRole('button', { name: 'Detect my location' })).toBeEnabled();
		await geo.answer(RIYADH.lat, RIYADH.lng, 10);
		await expect(pins).toHaveCount(0);
		await expect(coordinates).toHaveCount(0);
	});

	test('a refused permission says how to allow it, and what the browser said', async ({ page }) => {
		await scriptGeolocation(page);
		await signInAndStub(page);
		const geo = geoDriver(page);
		const { dialog } = await openAddLocation(page);

		await dialog.getByRole('button', { name: 'Detect my location' }).click();
		await geo.refuse(1, 'User denied Geolocation');

		const status = dialog.getByRole('status');
		await expect(status).toContainText('blocked for this site');
		await expect(status).toContainText('Your browser said: User denied Geolocation');
		await expect(dialog.getByRole('button', { name: 'Detect my location' })).toBeEnabled();
	});

	test('a browser that cannot find the device says so, with a hint that fits the platform', async ({
		page
	}) => {
		await scriptGeolocation(page);
		await signInAndStub(page);
		const geo = geoDriver(page);
		const { dialog } = await openAddLocation(page);
		const userAgent = await page.evaluate(() => navigator.userAgent);
		const onLinux = /linux/i.test(userAgent) && !/android/i.test(userAgent);

		await dialog.getByRole('button', { name: 'Detect my location' }).click();
		await geo.refuse(2, 'Unknown error acquiring position');
		await expect.poll(() => geo.watching()).toBe(1);
		await geo.failWatch(2, 'Unknown error acquiring position');

		const status = dialog.getByRole('status');
		await expect(status).toContainText('could not work out where you are');
		await expect(status).toContainText('Your browser said: Unknown error acquiring position');
		// The system-service hint is for Linux only; elsewhere it would be noise.
		if (onLinux) await expect(status).toContainText('Location Services');
		else await expect(status).not.toContainText('Location Services');
		await expect(status).toContainText('Click the map');
	});

	test('a timeout is called a timeout', async ({ page }) => {
		await scriptGeolocation(page);
		await signInAndStub(page);
		const geo = geoDriver(page);
		const { dialog } = await openAddLocation(page);

		await dialog.getByRole('button', { name: 'Detect my location' }).click();
		await geo.refuse(3, 'Timeout expired');
		await expect.poll(() => geo.watching()).toBe(1);
		await geo.failWatch(3, 'Timeout expired');

		await expect(dialog.getByRole('status')).toContainText('did not answer in time');
	});

	test('an insecure page is told why, without ever asking the browser', async ({ page }) => {
		await scriptGeolocation(page);
		await page.addInitScript(() =>
			Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true })
		);
		await signInAndStub(page);
		const geo = geoDriver(page);
		const { dialog } = await openAddLocation(page);

		await dialog.getByRole('button', { name: 'Detect my location' }).click();

		await expect(dialog.getByRole('status')).toContainText(
			'only shares your location with secure pages'
		);
		expect(await geo.asked()).toBe(0);
	});

	test("the browser's own provider: a rough fix from the real API places no pin", async ({
		page,
		context
	}) => {
		// No scripted provider: this goes through Chromium's real Geolocation API,
		// with a fix the test dictates.
		await context.grantPermissions(['geolocation']);
		await context.setGeolocation({ latitude: 24.7, longitude: 46.7, accuracy: 20_000 });
		await signInAndStub(page);
		const { dialog, pins } = await openAddLocation(page);
		const coordinates = dialog.locator('[data-coordinates]');

		await dialog.getByRole('button', { name: 'Detect my location' }).click();

		await expect(dialog.getByRole('status')).toContainText('too rough for a pin');
		await expect(pins).toHaveCount(0);
		await expect(coordinates).toHaveCount(0);
		await expect(circle(dialog)).toHaveCount(1);
	});
});
