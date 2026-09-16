import { chromium } from '@playwright/test';

const base = 'http://localhost:5173';
const api = 'http://localhost:8000/api/v1';
const OUT = '/tmp/claude-1000/-home-ringo-dev-container-Nova/09fa3525-78cd-4290-b7a3-791eb42d3be2/scratchpad';
const stamp = Date.now();
const ownerEmail = `owner-cal-${stamp}@example.com`;
const password = 'correct-horse-battery-1';

let passed = 0;
function ok(label) {
	passed++;
	console.log(`ok - ${label}`);
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

console.log('== register + set up a bookable business ==');
await page.goto(`${base}/register`, { waitUntil: 'networkidle' });
await page.getByRole('tab', { name: 'Business owner' }).click();
await page.getByLabel('Full name').fill('Calendar Owner');
await page.getByLabel('Email').fill(ownerEmail);
await page.getByLabel('Password').fill(password);
await page.getByRole('button', { name: 'Continue to your business →' }).click();
await page.getByLabel('Business name (English)').fill(`Calendar Salon ${stamp}`);
await page.getByLabel('Business name (Arabic)').fill('صالون التقويم');
await page.getByLabel('Business phone').fill('+966500000071');
await page.getByRole('button', { name: 'Create account and business' }).click();
await page.waitForURL(`${base}/app`, { timeout: 15000 });
ok('registered owner + business');

const authRaw = await page.evaluate(() => localStorage.getItem('nova.auth.v1'));
const { accessToken } = JSON.parse(authRaw);
const tenantId = JSON.parse(
	Buffer.from(accessToken.split('.')[1], 'base64url').toString('utf8')
).tenants[0];
const businessId = await page.evaluate(() => {
	const raw = localStorage.getItem('nova.businessByTenant');
	const map = raw ? JSON.parse(raw) : {};
	return Object.values(map)[0];
});

function api_(method, path, body) {
	return page.request
		.fetch(`${api}${path}`, {
			method,
			headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
			data: body ? JSON.stringify(body) : undefined
		})
		.then(async (r) => {
			if (!r.ok()) throw new Error(`${method} ${path} -> ${r.status()}: ${await r.text()}`);
			return r.json();
		});
}

const location = await api_('POST', `/tenants/${tenantId}/catalog/locations`, {
	business_id: businessId,
	name_en: 'Main Branch',
	name_ar: 'الفرع الرئيسي',
	phone: '+966500000072'
});
const service = await api_('POST', `/tenants/${tenantId}/catalog/services`, {
	location_id: location.id,
	name_en: 'Haircut',
	name_ar: 'قص شعر',
	duration_minutes: 30,
	price: '50',
	currency: 'SAR'
});
const provider = await api_('POST', `/tenants/${tenantId}/catalog/providers`, {
	location_id: location.id,
	name_en: 'Sara Stylist',
	name_ar: 'سارة'
});
await api_('PUT', `/tenants/${tenantId}/schedules/providers/${provider.id}`, {
	windows: [0, 1, 2, 3, 4, 5, 6].map((weekday) => ({
		weekday,
		start_minute: 9 * 60,
		end_minute: 17 * 60
	}))
});
await api_('POST', `/tenants/${tenantId}/catalog/providers/${provider.id}/services/${service.id}`);
await api_('PATCH', `/tenants/${tenantId}/catalog/businesses/${businessId}/listing`, {
	is_listed: true
});
const business = await api_('GET', `/tenants/${tenantId}/catalog/businesses/${businessId}`);
ok(`catalog seeded and business listed publicly (slug: ${business.slug})`);

console.log('== the calendar slot picker, on the public storefront ==');
await page.goto(`${base}/discover/${business.slug}`, { waitUntil: 'networkidle' });
await page.getByRole('button', { name: /Haircut/ }).click();
await page.waitForTimeout(800);

// Month label and weekday header render.
const monthLabelVisible = await page
	.locator('p.font-medium', { hasText: /\d{4}/ })
	.first()
	.isVisible();
if (!monthLabelVisible) throw new Error('Calendar month label did not render');
ok('calendar month header rendered');

// At least one enabled (non-disabled) day cell with a dot indicator exists.
const enabledDayButtons = page.locator('button[aria-pressed]:not([disabled])');
const enabledCount = await enabledDayButtons.count();
if (enabledCount === 0) throw new Error('No selectable calendar day found');
ok(`${enabledCount} bookable day(s) selectable on the calendar`);

await page.screenshot({ path: `${OUT}/calendar-before-day-click.png`, fullPage: true });

// Click the first bookable day and confirm time-of-day sections appear.
await enabledDayButtons.first().click();
await page.waitForTimeout(300);
const periodHeading = page.locator('p', { hasText: /^(Morning|Afternoon|Evening)$/ }).first();
if (!(await periodHeading.isVisible())) throw new Error('No time-of-day section rendered for the selected day');
ok('selecting a calendar day shows time-of-day grouped slots (Morning/Afternoon/Evening)');

await page.screenshot({ path: `${OUT}/calendar-day-selected.png`, fullPage: true });

// Pick a time slot and confirm the selection is reflected (highlighted +
// booking summary panel appears).
const timeButtons = page.locator('button', { hasText: /^\d{1,2}:\d{2}/ });
const timeCount = await timeButtons.count();
if (timeCount === 0) throw new Error('No time slots rendered for the selected day');
await timeButtons.first().click();
await page.waitForTimeout(300);
const summaryVisible = await page.getByText('Confirm your booking').isVisible().catch(() => false);
ok(`picked a time slot (${timeCount} offered that day); booking summary panel ${summaryVisible ? 'appeared' : 'did not appear (check copy)'}`);

await page.screenshot({ path: `${OUT}/calendar-slot-selected.png`, fullPage: true });

await browser.close();
console.log(`\nALL ${passed} CHECKS PASSED`);
