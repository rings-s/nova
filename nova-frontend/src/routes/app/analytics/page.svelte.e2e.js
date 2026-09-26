import { expect, test } from '@playwright/test';

// The analytics page against a stubbed API, in the shape the real endpoints
// return (`nova_backend/app/modules/analytics/schemas.py`; each chart's
// `figure` is Plotly JSON, as `charts.py` builds it).

const TENANT = 'tenant-analytics';
const BUSINESS = 'business-analytics';
const cors = { 'access-control-allow-origin': '*' };

/** @param {object} value */
const base64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

const CATALOG = [
	['bookings_trend', 'stacked_bar', 'Bookings and how they ended', null],
	['booking_outcomes', 'donut', 'Booking outcomes', null],
	['revenue_by_service', 'bar', 'Revenue by service', null],
	['revenue_by_location', 'bar', 'Revenue by branch', 'multi_location']
].map(([chart_id, kind, title_en, required_feature]) => ({
	chart_id,
	kind,
	title_en,
	title_ar: title_en,
	question_en: `${title_en}?`,
	question_ar: '',
	required_feature
}));

/** @type {Record<string, object[]>} */
const FIGURES = {
	bookings_trend: [
		{
			type: 'bar',
			name: 'Completed',
			marker: { color: '#16a34a' },
			x: ['2026-09-01', '2026-09-02'],
			y: [4, 6]
		},
		{
			type: 'bar',
			name: 'Cancelled',
			marker: { color: '#9ca3af' },
			x: ['2026-09-01', '2026-09-02'],
			y: [1, 0]
		}
	],
	booking_outcomes: [
		{
			type: 'pie',
			hole: 0.55,
			labels: ['Completed', 'Cancelled', 'No-show'],
			values: [18, 1, 1]
		}
	],
	revenue_by_service: [
		{ type: 'bar', orientation: 'h', y: ['Signature Facial', 'Hot Stone Massage'], x: [950, 4800] }
	]
};

/** @param {boolean} previous */
const kpis = (previous) =>
	[
		['revenue', 'money', previous ? '4000.00' : '4800.00'],
		['average_ticket', 'money', '240.00'],
		['bookings', 'count', previous ? '16' : '20'],
		['completion_rate', 'ratio', previous ? '0.8000' : '0.9000'],
		['no_show_rate', 'ratio', previous ? '0.1000' : '0.0500'],
		['new_customers', 'count', '5'],
		['average_queue_wait_minutes', 'minutes', '12.5'],
		['repeat_rate', 'ratio', null]
	].map(([metric, unit, value]) => ({
		metric,
		unit,
		value,
		sample_size: value === null ? 2 : 20,
		suppressed: value === null
	}));

/**
 * @param {import('@playwright/test').Page} page
 * @returns {Promise<URL[]>} the API requests the page made
 */
async function openAnalytics(page) {
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

	/** @type {URL[]} */ const calls = [];
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
		const url = new URL(request.url());
		calls.push(url);
		const path = url.pathname.replace(/^.*\/api\/v1/, '');
		const json = (/** @type {object} */ body) => route.fulfill({ headers: cors, json: body });

		if (path === `/tenants/${TENANT}/memberships/me`) {
			return json({ role: 'owner', permissions: ['view_analytics'], manageable_roles: [] });
		}
		if (path === '/tenants') {
			return json({ items: [{ id: TENANT, name_en: 'Numbers Spa', name_ar: 'سبا' }] });
		}
		if (path.endsWith('/billing/plans')) {
			return json({ items: [{ tier: 'solo', included_features: [] }] });
		}
		if (path.endsWith(`/billing/subscriptions/${BUSINESS}`)) {
			return route.fulfill({
				status: 404,
				headers: cors,
				json: { error: { code: 'not_found', message: 'No subscription' } }
			});
		}
		if (path.endsWith('/analytics/charts')) return json({ items: CATALOG });
		if (path.includes('/analytics/charts/')) {
			const id = /** @type {string} */ (path.split('/').pop());
			const entry = CATALOG.find((c) => c.chart_id === id);
			return json({
				chart_id: id,
				kind: entry?.kind ?? 'bar',
				title: entry?.title_en ?? id,
				description: '',
				figure: { data: FIGURES[id] ?? [], layout: {} },
				currency: 'SAR'
			});
		}
		if (path.endsWith('/analytics/overview')) {
			const dateTo = /** @type {string} */ (url.searchParams.get('date_to'));
			const isPrevious = dateTo < new Date().toISOString().slice(0, 10);
			return json({
				business_id: BUSINESS,
				window: {
					date_from: url.searchParams.get('date_from'),
					date_to: dateTo,
					timezone: 'Asia/Riyadh',
					days: 30
				},
				currency: 'SAR',
				excluded_rows: 0,
				kpis: kpis(isPrevious)
			});
		}
		if (path.endsWith('/analytics/breakdown')) {
			return json({
				items: [
					{
						dimension: 'service',
						key: 'svc-1',
						label: 'Hot Stone Massage',
						label_en: 'Hot Stone Massage',
						label_ar: '',
						bookings: 12,
						completed: 11,
						revenue: '4800.00',
						share_of_revenue: '0.8348'
					}
				]
			});
		}
		return json({ items: [] });
	});

	await page.goto('/app/analytics');
	return calls;
}

test.use({ viewport: { width: 1280, height: 900 } });

test('each KPI is written in its own unit, with its change against the window before', async ({
	page
}) => {
	await openAnalytics(page);
	const headline = page.getByRole('region', { name: 'Headline' });

	await expect(headline.getByText('SAR 4,800', { exact: true })).toBeVisible();
	// 4,000 → 4,800: a 20% rise.
	await expect(headline.getByText('20.0%')).toBeVisible();
	// A rate is a fraction on the wire and moves in percentage points.
	await expect(headline.getByText('90%')).toBeVisible();
	await expect(headline.getByText('10.0 pts')).toBeVisible();

	// Too small a sample is a dash, never a zero.
	await expect(page.getByText('Too few bookings to tell yet').first()).toBeVisible();
	await expect(page.getByText('12.5 min')).toBeVisible();
});

test('the comparison window has the same length and ends the day before', async ({ page }) => {
	const calls = await openAnalytics(page);
	await expect(page.getByRole('region', { name: 'Headline' })).toBeVisible();

	await page.getByRole('radio', { name: '7 days' }).click();
	await expect
		.poll(() => calls.filter((u) => u.pathname.endsWith('/overview')).length)
		.toBeGreaterThanOrEqual(4);

	const windows = calls
		.filter((u) => u.pathname.endsWith('/overview'))
		.slice(-2)
		.map((u) => ({ from: u.searchParams.get('date_from'), to: u.searchParams.get('date_to') }))
		.sort((a, b) => String(a.to).localeCompare(String(b.to)));
	const day = (/** @type {string|null} */ d) => Date.parse(`${d}T00:00:00Z`) / 864e5;
	const [before, current] = windows;
	expect(day(current.to) - day(current.from)).toBe(6);
	expect(day(before.to) - day(before.from)).toBe(6);
	expect(day(current.from) - day(before.to)).toBe(1);
});

test('a donut is drawn as a part-to-whole bar, and every chart has a table view', async ({
	page
}) => {
	await openAnalytics(page);

	const outcomes = page.getByRole('region', { name: 'Booking outcomes' });
	await expect(outcomes.getByText('90%', { exact: true }).first()).toBeVisible();
	await expect(outcomes.getByRole('img', { name: /Completed 90%/ })).toBeVisible();

	const services = page.getByRole('region', { name: 'Revenue by service' });
	// Ranked largest first, whatever order the figure lists them in.
	await expect(services.getByRole('listitem').first()).toContainText('Hot Stone Massage');
	await services.getByRole('button', { name: 'Show as table' }).click();
	await expect(services.getByRole('row', { name: /Signature Facial/ })).toContainText('SAR 950.00');
});

test('a chart the plan lacks is shown locked and never requested', async ({ page }) => {
	const calls = await openAnalytics(page);

	const branch = page.getByRole('region', { name: 'Revenue by branch' });
	await expect(branch.getByText('Not in your current plan')).toBeVisible();
	await expect(
		page.getByRole('region', { name: 'Revenue by service' }).getByRole('list')
	).toBeVisible();
	expect(calls.some((u) => u.pathname.endsWith('/charts/revenue_by_location'))).toBe(false);
});

test('the breakdown shows each row with its share of revenue', async ({ page }) => {
	await openAnalytics(page);
	const row = page.getByRole('row', { name: /Hot Stone Massage/ }).last();
	await expect(row).toContainText('SAR 4,800');
	await expect(row).toContainText('83.5%');
});
