import { expect, test } from '@playwright/test';

// The marketplace assistant books only a held time the customer pressed "Yes,
// book it" on: the button sends that hold's token (`confirm_hold_token`), and
// the agent's `book_held_slot` refuses any other confirmation, a "yes" typed
// in words included (ADR-0015). Against a stubbed API.

const cors = { 'access-control-allow-origin': '*' };
const HOLD_TOKEN = 'hold-token-1';

/** @param {object} value */
const base64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

/** @param {Partial<import('../../lib/api/ai.js').AiChatResponse>} fields */
function turn(fields) {
	return {
		session_id: 's',
		agent: 'marketplace_agent',
		reply: '',
		suggested_actions: [],
		requires_human_handoff: false,
		related_booking_id: null,
		related_ticket_url: null,
		held_slots: [],
		queue_places: [],
		pending_cancellations: [],
		degraded: false,
		confidence: 1,
		metrics_used: [],
		charts: [],
		proposed_actions: [],
		tickets: [],
		...fields
	};
}

/** @param {import('@playwright/test').Page} page @returns {Promise<any[]>} chat request bodies */
async function signInAsCustomer(page) {
	const now = Math.floor(Date.now() / 1000);
	const token = [
		base64url({ alg: 'HS256', typ: 'JWT' }),
		base64url({
			sub: 'user-1',
			kind: 'customer',
			tenants: [],
			roles: [],
			iat: now,
			exp: now + 3600
		}),
		'signature'
	].join('.');
	await page.addInitScript((accessToken) => {
		localStorage.setItem('nova.auth.v1', JSON.stringify({ accessToken, refreshToken: 'r' }));
	}, token);

	await page.route('https://tile.openstreetmap.org/**', (route) =>
		route.fulfill({
			contentType: 'image/svg+xml',
			body: '<svg xmlns="http://www.w3.org/2000/svg"/>'
		})
	);
	/** @type {any[]} */ const chats = [];
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
		if (path === '/discovery/ai/status') {
			return route.fulfill({ headers: cors, json: { inference_available: true } });
		}
		if (path === '/discovery/ai/chat') {
			const body = request.postDataJSON();
			chats.push(body);
			const startsAt = new Date(Date.now() + 2 * 86_400_000).toISOString();
			return route.fulfill({
				headers: cors,
				json: body.confirm_hold_token
					? turn({ reply: 'Booked.' })
					: turn({
							reply: 'I am holding that time. Shall I book it?',
							held_slots: [
								{
									hold_token: HOLD_TOKEN,
									provider_id: 'p-1',
									service_id: 's-1',
									location_id: 'l-1',
									starts_at: startsAt,
									ends_at: startsAt,
									expires_at: new Date(Date.now() + 600_000).toISOString()
								}
							]
						})
			});
		}
		if (path === '/discovery/map') {
			return route.fulfill({
				headers: cors,
				json: { type: 'FeatureCollection', truncated: false, features: [] }
			});
		}
		return route.fulfill({ headers: cors, json: { items: [] } });
	});
	return chats;
}

test('only the "Yes, book it" button confirms a held time, by its hold token', async ({ page }) => {
	const chats = await signInAsCustomer(page);
	await page.goto('/discover');

	// The launcher appears once the page has hydrated and the status answered.
	await page.getByRole('button', { name: 'Ask the assistant' }).click();
	const box = page.getByPlaceholder('Type a message…');
	await box.fill('A haircut the day after tomorrow');
	await box.press('Enter');

	await page.getByRole('button', { name: 'Yes, book it' }).click();
	await expect(page.getByText('Booked.')).toBeVisible();

	expect(chats).toHaveLength(2);
	// Typed text carries no confirmation, however it is worded.
	expect(chats[0].confirm_hold_token).toBeNull();
	expect(chats[1].confirm_hold_token).toBe(HOLD_TOKEN);
});
