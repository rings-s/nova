import { json } from '@sveltejs/kit';

// In-memory mock database for NOVA platform
const nowIso = new Date().toISOString();

const mockData = {
	tenants: [
		{
			id: 'tenant-1',
			name_en: 'Lumière Wellness & Spa',
			name_ar: 'سبا ومركز لوميير للعناية',
			slug: 'lumiere-salon',
			phone: '+966501234567',
			default_currency: 'SAR',
			created_at: '2026-01-15T09:00:00Z',
			updated_at: '2026-01-15T09:00:00Z'
		}
	],
	businesses: [
		{
			id: 'biz-1',
			tenant_id: 'tenant-1',
			name_en: 'Lumière Wellness & Spa',
			name_ar: 'سبا ومركز لوميير للعناية',
			slug: 'lumiere-salon',
			description_en: 'Premium beauty, skincare, and wellness sanctuary in Riyadh.',
			description_ar: 'ملاذ فاخر للجمال والعناية بالبشرة والاسترخاء في الرياض.',
			logo_asset_id: null,
			cover_asset_id: null,
			is_active: true,
			is_listed: true,
			created_at: '2026-01-15T09:00:00Z',
			updated_at: '2026-01-15T09:00:00Z'
		}
	],
	locations: [
		{
			id: 'loc-1',
			tenant_id: 'tenant-1',
			business_id: 'biz-1',
			name_en: 'Al Olaya Flagship',
			name_ar: 'فرع العليا الرئيسي',
			slug: 'olaya-flagship',
			phone: '+966501234567',
			timezone: 'Asia/Riyadh',
			city: 'Riyadh',
			latitude: 24.7136,
			longitude: 46.6753,
			is_active: true,
			created_at: '2026-01-15T09:00:00Z',
			updated_at: '2026-01-15T09:00:00Z'
		}
	],
	providers: [
		{
			id: 'prov-1',
			tenant_id: 'tenant-1',
			location_id: 'loc-1',
			name_en: 'Nour Al-Sabah',
			name_ar: 'نور الصباح',
			title_en: 'Senior Stylist & Esthetician',
			title_ar: 'أخصائية تجميل وعناية بالبشرة',
			image_asset_id: null,
			is_active: true,
			created_at: '2026-01-15T09:00:00Z',
			updated_at: '2026-01-15T09:00:00Z'
		},
		{
			id: 'prov-2',
			tenant_id: 'tenant-1',
			location_id: 'loc-1',
			name_en: 'Layla Mahmoud',
			name_ar: 'ليلى محمود',
			title_en: 'Massage Therapist & Spa Specialist',
			title_ar: 'أخصائية تدليك وعلاجات سبا',
			image_asset_id: null,
			is_active: true,
			created_at: '2026-01-15T09:00:00Z',
			updated_at: '2026-01-15T09:00:00Z'
		}
	],
	services: [
		{
			id: 'srv-1',
			tenant_id: 'tenant-1',
			location_id: 'loc-1',
			name_en: 'HydraFacial Glow Treatment',
			name_ar: 'جلسة هيدرافيشل لنضارة البشرة',
			description_en:
				'Deep cleansing, gentle exfoliation, and intense hydration with nourishing peptides.',
			description_ar: 'تنظيف عميق وتقشير لطيف وترطيب مكثف مع سيروم الببتيدات المغذية.',
			category: 'Skincare',
			duration_minutes: 60,
			price: '450.00',
			currency: 'SAR',
			is_active: true,
			created_at: '2026-01-15T09:00:00Z',
			updated_at: '2026-01-15T09:00:00Z'
		},
		{
			id: 'srv-2',
			tenant_id: 'tenant-1',
			location_id: 'loc-1',
			name_en: 'Royal Moroccan Bath & Ritual',
			name_ar: 'حمام مغربي ملكي وطقوس استرخاء',
			description_en:
				'Authentic Moroccan hammam ritual with herbal steam and black soap treatment.',
			description_ar: 'جلسة حمام مغربي أصيل بالبخار بالأعشاب والصابون البلدي.',
			category: 'Spa & Body',
			duration_minutes: 75,
			price: '380.00',
			currency: 'SAR',
			is_active: true,
			created_at: '2026-01-15T09:00:00Z',
			updated_at: '2026-01-15T09:00:00Z'
		},
		{
			id: 'srv-3',
			tenant_id: 'tenant-1',
			location_id: 'loc-1',
			name_en: 'Signature Haircut & Blowout',
			name_ar: 'قص شعر وتصفيف احترافي',
			description_en: 'Custom precision haircut and luxury botanical blowout styling.',
			description_ar: 'قص شعر بتنسيق مخصص وتصفيف فاخر باستخدام مستحضرات طبيعية.',
			category: 'Hair',
			duration_minutes: 45,
			price: '220.00',
			currency: 'SAR',
			is_active: true,
			created_at: '2026-01-15T09:00:00Z',
			updated_at: '2026-01-15T09:00:00Z'
		}
	],
	customers: [
		{
			id: 'cust-1',
			tenant_id: 'tenant-1',
			full_name: 'Sara Al-Otaibi',
			phone: '+966551122334',
			email: 'sara.otaibi@example.com',
			preferred_language: 'ar',
			marketing_consent: true,
			whatsapp_consent: true,
			notes: 'Prefers lavender essential oils',
			created_at: '2026-02-01T10:00:00Z',
			updated_at: '2026-02-01T10:00:00Z'
		},
		{
			id: 'cust-2',
			tenant_id: 'tenant-1',
			full_name: 'Reem Al-Hassan',
			phone: '+966559988776',
			email: 'reem.hassan@example.com',
			preferred_language: 'en',
			marketing_consent: false,
			whatsapp_consent: true,
			notes: 'Sensitive skin',
			created_at: '2026-02-10T14:30:00Z',
			updated_at: '2026-02-10T14:30:00Z'
		}
	],
	bookings: [
		{
			id: 'bk-1',
			tenant_id: 'tenant-1',
			business_id: 'biz-1',
			location_id: 'loc-1',
			service_id: 'srv-1',
			provider_id: 'prov-1',
			customer_id: 'cust-1',
			starts_at: new Date(Date.now() + 3600000).toISOString(),
			ends_at: new Date(Date.now() + 7200000).toISOString(),
			price: '450.00',
			currency: 'SAR',
			status: 'confirmed',
			source: 'marketplace',
			cancellation_reason: null,
			notes: 'VIP customer'
		},
		{
			id: 'bk-2',
			tenant_id: 'tenant-1',
			business_id: 'biz-1',
			location_id: 'loc-1',
			service_id: 'srv-2',
			provider_id: 'prov-2',
			customer_id: 'cust-2',
			starts_at: new Date(Date.now() + 10800000).toISOString(),
			ends_at: new Date(Date.now() + 15300000).toISOString(),
			price: '380.00',
			currency: 'SAR',
			status: 'confirmed',
			source: 'direct_link',
			cancellation_reason: null,
			notes: null
		}
	],
	queues: [
		{
			id: 'q-1',
			tenant_id: 'tenant-1',
			location_id: 'loc-1',
			name_en: 'Express Walk-in Lounge',
			name_ar: 'صالة الاستقبال السريع للزوار',
			is_open: true,
			average_service_minutes: 30
		}
	],
	queue_entries: [
		{
			id: 'qe-1',
			queue_id: 'q-1',
			location_id: 'loc-1',
			customer_id: 'cust-1',
			service_id: 'srv-3',
			provider_id: 'prov-1',
			status: 'waiting',
			source: 'walk_in',
			position: 1,
			party_size: 1,
			booking_id: null,
			joined_at: new Date(Date.now() - 900000).toISOString(),
			called_at: null,
			place_in_line: 1,
			estimated_wait_minutes: 10
		}
	],
	memberships: [
		{
			id: 'mem-1',
			tenant_id: 'tenant-1',
			user_id: 'user-1',
			email: 'admin@nova.sa',
			full_name: 'Nova Admin',
			role: 'owner',
			is_active: true,
			created_at: '2026-01-15T09:00:00Z',
			updated_at: '2026-01-15T09:00:00Z'
		}
	],
	plans: [
		{
			tier: 'solo',
			monthly_price: '199.00',
			annual_price: '1990.00',
			currency: 'SAR',
			new_client_commission_pct: '12.0',
			repeat_commission_pct: '0.0',
			processing_fee_pct: '2.5',
			included_features: ['calendar', 'booking', 'walk_in', 'whatsapp_notifications'],
			priced_per_location: false,
			max_seats: 1,
			max_locations: 1
		},
		{
			tier: 'studio',
			monthly_price: '499.00',
			annual_price: '4990.00',
			currency: 'SAR',
			new_client_commission_pct: '10.0',
			repeat_commission_pct: '0.0',
			processing_fee_pct: '2.2',
			included_features: [
				'calendar',
				'booking',
				'walk_in',
				'whatsapp_notifications',
				'view_analytics',
				'ai_assistant',
				'custom_branding'
			],
			priced_per_location: false,
			max_seats: 5,
			max_locations: 2
		},
		{
			tier: 'chain',
			monthly_price: '1199.00',
			annual_price: '11990.00',
			currency: 'SAR',
			new_client_commission_pct: '8.0',
			repeat_commission_pct: '0.0',
			processing_fee_pct: '2.0',
			included_features: [
				'calendar',
				'booking',
				'walk_in',
				'whatsapp_notifications',
				'view_analytics',
				'view_financials',
				'ai_assistant',
				'multi_branch',
				'api_access'
			],
			priced_per_location: true,
			max_seats: null,
			max_locations: null
		}
	],
	subscription: {
		id: 'sub-1',
		business_id: 'biz-1',
		tier: 'studio',
		status: 'active',
		current_period_start: '2026-09-01T00:00:00Z',
		current_period_end: '2026-10-01T00:00:00Z',
		seats: 5,
		locations: 2,
		cancel_at_period_end: false,
		monthly_amount: '499.00',
		currency: 'SAR',
		marketplace_listing_hidden: false
	}
};

// Generate base64 JWT with claims
function createMockJwt(email = 'admin@nova.sa', role = 'owner', tenantId = 'tenant-1') {
	const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
	const exp = Math.floor(Date.now() / 1000) + 86400 * 30;
	const payloadObj = {
		sub: 'usr-1',
		email,
		kind: 'staff',
		tenants: [tenantId],
		roles: [role],
		exp,
		iat: Math.floor(Date.now() / 1000)
	};
	const payload = btoa(JSON.stringify(payloadObj))
		.replace(/\+/g, '-')
		.replace(/\//g, '_')
		.replace(/=+$/, '');
	return `${header}.${payload}.signature_mock`;
}

/**
 * @param {Request} request
 * @param {{ path?: string }} params
 * @param {URL} url
 * @param {'GET'|'POST'|'PUT'|'PATCH'|'DELETE'} method
 */
async function handleRequest(request, params, url, method) {
	const path = (params.path || '').replace(/^\/+/, '').replace(/\/+$/, '');
	const query = Object.fromEntries(url.searchParams.entries());

	let body = null;
	if (['POST', 'PUT', 'PATCH'].includes(method)) {
		try {
			body = await request.json();
		} catch {
			body = {};
		}
	}

	// 1. Auth routes
	if (path === 'auth/login') {
		const email = body?.email || 'admin@nova.sa';
		const token = createMockJwt(email, 'owner', 'tenant-1');
		return json({
			access_token: token,
			refresh_token: 'mock-refresh-token-' + Date.now(),
			token_type: 'bearer',
			expires_in: 86400 * 30
		});
	}

	if (path === 'auth/refresh') {
		const token = createMockJwt('admin@nova.sa', 'owner', 'tenant-1');
		return json({
			access_token: token,
			refresh_token: 'mock-refresh-token-' + Date.now(),
			token_type: 'bearer',
			expires_in: 86400 * 30
		});
	}

	if (path === 'auth/register') {
		return json({
			id: 'usr-' + Date.now(),
			email: body?.email || 'new@nova.sa',
			full_name: body?.full_name || 'New User'
		});
	}

	if (path === 'auth/logout-everywhere') {
		return json({ success: true });
	}

	// 2. Discovery routes (public marketplace)
	// The public projection of one branch: what `ListingCardOut` carries in the real API.
	/** @param {(typeof mockData.businesses)[number]} biz */
	const listingCard = (biz) => {
		const loc = mockData.locations.find((l) => l.business_id === biz.id) || mockData.locations[0];
		const startingSrv = mockData.services.find((s) => s.tenant_id === biz.tenant_id);
		return {
			business_id: biz.id,
			tenant_id: biz.tenant_id,
			slug: biz.slug,
			name_en: biz.name_en,
			name_ar: biz.name_ar,
			description_en: biz.description_en,
			description_ar: biz.description_ar,
			logo_asset_id: biz.logo_asset_id,
			cover_asset_id: biz.cover_asset_id,
			location_id: loc.id,
			location_name_en: loc.name_en,
			location_name_ar: loc.name_ar,
			city: loc.city,
			latitude: loc.latitude,
			longitude: loc.longitude,
			timezone: loc.timezone,
			starting_price: startingSrv?.price || '220.00',
			currency: 'SAR',
			distance_km: 2.4
		};
	};

	if (path === 'discovery/businesses') {
		const items = mockData.businesses.map(listingCard);
		return json({ items, total: items.length });
	}

	// The same listings as GeoJSON for the Leaflet map. Like the route above, the
	// mock ignores filters; it only has to hand back the right shape.
	if (path === 'discovery/map') {
		const features = mockData.businesses
			.map(listingCard)
			.filter((card) => card.latitude != null && card.longitude != null)
			.map((card) => ({
				type: 'Feature',
				id: card.location_id,
				// GeoJSON is [longitude, latitude].
				geometry: { type: 'Point', coordinates: [card.longitude, card.latitude] },
				properties: card
			}));
		return json({ type: 'FeatureCollection', features, truncated: false });
	}

	if (path.startsWith('discovery/businesses/')) {
		const parts = path.split('/');
		const slug = parts[2];
		const sub = parts[3];

		const biz = mockData.businesses.find((b) => b.slug === slug) || mockData.businesses[0];
		const locs = mockData.locations.filter((l) => l.business_id === biz.id);
		const srvs = mockData.services.filter((s) => s.tenant_id === biz.tenant_id);
		const provs = mockData.providers.filter((p) => p.tenant_id === biz.tenant_id);

		if (sub === 'services' && parts[5] === 'availability') {
			const srvId = parts[4];
			const slots = [
				{
					slot_id: 'slot-1',
					provider_id: provs[0]?.id || 'prov-1',
					provider_name_en: provs[0]?.name_en || 'Nour Al-Sabah',
					provider_name_ar: provs[0]?.name_ar || 'نور الصباح',
					location_id: locs[0]?.id || 'loc-1',
					service_id: srvId,
					starts_at: new Date(Date.now() + 86400000).toISOString(),
					ends_at: new Date(Date.now() + 90000000).toISOString()
				},
				{
					slot_id: 'slot-2',
					provider_id: provs[1]?.id || 'prov-2',
					provider_name_en: provs[1]?.name_en || 'Layla Mahmoud',
					provider_name_ar: provs[1]?.name_ar || 'ليلى محمود',
					location_id: locs[0]?.id || 'loc-1',
					service_id: srvId,
					starts_at: new Date(Date.now() + 93600000).toISOString(),
					ends_at: new Date(Date.now() + 97200000).toISOString()
				}
			];
			return json({ business_id: biz.id, slots });
		}

		if (sub === 'referrals') {
			return json({ referral_token: 'ref-' + Date.now(), recorded_at: nowIso });
		}

		// Storefront detail
		return json({
			business_id: biz.id,
			tenant_id: biz.tenant_id,
			slug: biz.slug,
			name_en: biz.name_en,
			name_ar: biz.name_ar,
			description_en: biz.description_en,
			description_ar: biz.description_ar,
			logo_asset_id: biz.logo_asset_id,
			cover_asset_id: biz.cover_asset_id,
			locations: locs.map((l) => ({
				id: l.id,
				name_en: l.name_en,
				name_ar: l.name_ar,
				city: l.city,
				phone: l.phone,
				timezone: l.timezone,
				latitude: l.latitude,
				longitude: l.longitude
			})),
			services: srvs.map((s) => ({
				id: s.id,
				location_id: s.location_id,
				name_en: s.name_en,
				name_ar: s.name_ar,
				description_en: s.description_en,
				description_ar: s.description_ar,
				category: s.category,
				duration_minutes: s.duration_minutes,
				price: s.price,
				currency: s.currency
			})),
			providers: provs.map((p) => ({
				id: p.id,
				location_id: p.location_id,
				name_en: p.name_en,
				name_ar: p.name_ar,
				title_en: p.title_en,
				title_ar: p.title_ar,
				image_asset_id: p.image_asset_id
			}))
		});
	}

	// 3. Root Tenants routes
	if (path === 'tenants') {
		if (method === 'POST') {
			const newTenant = {
				id: 'tenant-' + (mockData.tenants.length + 1),
				name_en: body?.name_en || 'My Business',
				name_ar: body?.name_ar || 'مشروعي',
				slug: (body?.name_en || 'my-business').toLowerCase().replace(/\s+/g, '-'),
				phone: body?.phone || '+966500000000',
				default_currency: body?.default_currency || 'SAR',
				created_at: nowIso,
				updated_at: nowIso
			};
			mockData.tenants.push(newTenant);
			return json(newTenant);
		}
		return json({ items: mockData.tenants, total: mockData.tenants.length });
	}

	// 4. Tenant-scoped routes
	if (path.startsWith('tenants/')) {
		const parts = path.split('/');
		const tenantId = parts[1];
		const section = parts[2];
		const subId = parts[3];

		// GET /tenants/:id
		if (!section) {
			const t = mockData.tenants.find((item) => item.id === tenantId) || mockData.tenants[0];
			return json(t);
		}

		// Catalog
		if (section === 'catalog') {
			const sub = parts[3]; // businesses, locations, services, providers
			const itemId = parts[4];

			if (sub === 'businesses') {
				if (itemId) {
					const b = mockData.businesses.find((x) => x.id === itemId) || mockData.businesses[0];
					return json(b);
				}
				if (method === 'POST') {
					const newBiz = {
						id: 'biz-' + (mockData.businesses.length + 1),
						tenant_id: tenantId,
						name_en: body?.name_en || 'New Business',
						name_ar: body?.name_ar || 'عمل جديد',
						slug: (body?.name_en || 'biz').toLowerCase().replace(/\s+/g, '-'),
						description_en: body?.description_en || null,
						description_ar: body?.description_ar || null,
						logo_asset_id: null,
						cover_asset_id: null,
						is_active: true,
						is_listed: true,
						created_at: nowIso,
						updated_at: nowIso
					};
					mockData.businesses.push(newBiz);
					return json(newBiz);
				}
				return json({ items: mockData.businesses, total: mockData.businesses.length });
			}

			if (sub === 'locations') {
				// PATCH .../locations/:id/position — set, move or clear a branch's map pin.
				if (itemId && parts[5] === 'position' && method === 'PATCH') {
					const loc = mockData.locations.find((x) => x.id === itemId);
					if (!loc) {
						return json(
							{ error: { code: 'location_not_found', message: 'Location was not found.' } },
							{ status: 404 }
						);
					}
					const { latitude = null, longitude = null } = body ?? {};
					// The real API takes both numbers or neither.
					if ((latitude === null) !== (longitude === null)) {
						return json(
							{
								error: {
									code: 'validation_error',
									message: 'Latitude and longitude must be provided together.'
								}
							},
							{ status: 422 }
						);
					}
					loc.latitude = latitude;
					loc.longitude = longitude;
					loc.updated_at = new Date().toISOString();
					return json(loc);
				}
				if (itemId) {
					return json(mockData.locations.find((x) => x.id === itemId) || mockData.locations[0]);
				}
				if (method === 'POST') {
					const newLoc = {
						id: 'loc-' + (mockData.locations.length + 1),
						tenant_id: tenantId,
						business_id: body?.business_id || mockData.businesses[0]?.id || 'biz-1',
						name_en: body?.name_en || 'New Branch',
						name_ar: body?.name_ar || 'فرع جديد',
						slug: (body?.name_en || 'branch').toLowerCase().replace(/\s+/g, '-'),
						phone: body?.phone || '',
						timezone: body?.timezone || 'Asia/Riyadh',
						city: body?.city ?? null,
						latitude: body?.latitude ?? null,
						longitude: body?.longitude ?? null,
						is_active: true,
						created_at: nowIso,
						updated_at: nowIso
					};
					mockData.locations.push(newLoc);
					return json(newLoc);
				}
				return json({ items: mockData.locations, total: mockData.locations.length });
			}

			if (sub === 'services') {
				if (itemId) {
					return json(mockData.services.find((x) => x.id === itemId) || mockData.services[0]);
				}
				if (method === 'POST') {
					const newSrv = {
						id: 'srv-' + (mockData.services.length + 1),
						tenant_id: tenantId,
						location_id: body?.location_id || mockData.locations[0].id,
						name_en: body?.name_en || 'Service',
						name_ar: body?.name_ar || 'خدمة',
						description_en: body?.description_en || null,
						description_ar: body?.description_ar || null,
						category: body?.category || 'General',
						duration_minutes: body?.duration_minutes || 60,
						price: String(body?.price || '200.00'),
						currency: body?.currency || 'SAR',
						is_active: true,
						created_at: nowIso,
						updated_at: nowIso
					};
					mockData.services.push(newSrv);
					return json(newSrv);
				}
				return json({ items: mockData.services, total: mockData.services.length });
			}

			if (sub === 'providers') {
				if (itemId) {
					return json(mockData.providers.find((x) => x.id === itemId) || mockData.providers[0]);
				}
				return json({ items: mockData.providers, total: mockData.providers.length });
			}
		}

		// Bookings
		if (section === 'bookings') {
			if (subId === 'availability') {
				const slots = [
					{
						slot_id: 'slot-avail-1',
						provider_id: mockData.providers[0]?.id || 'prov-1',
						location_id: mockData.locations[0]?.id || 'loc-1',
						service_id: query.service_id || mockData.services[0]?.id || 'srv-1',
						starts_at: new Date(Date.now() + 3600000).toISOString(),
						ends_at: new Date(Date.now() + 7200000).toISOString(),
						remaining_capacity: 1
					},
					{
						slot_id: 'slot-avail-2',
						provider_id: mockData.providers[1]?.id || 'prov-2',
						location_id: mockData.locations[0]?.id || 'loc-1',
						service_id: query.service_id || mockData.services[0]?.id || 'srv-1',
						starts_at: new Date(Date.now() + 14400000).toISOString(),
						ends_at: new Date(Date.now() + 18000000).toISOString(),
						remaining_capacity: 1
					}
				];
				return json({ items: slots, total: slots.length });
			}

			if (subId === 'holds') {
				return json({
					hold_token: 'hold-' + Date.now(),
					provider_id: body?.provider_id || 'prov-1',
					service_id: body?.service_id || 'srv-1',
					starts_at: body?.starts_at || nowIso,
					ends_at: new Date(Date.now() + 3600000).toISOString(),
					expires_at: new Date(Date.now() + 600000).toISOString()
				});
			}

			if (method === 'POST' && !subId) {
				const newBooking = {
					id: 'bk-' + (mockData.bookings.length + 1),
					tenant_id: tenantId,
					business_id: mockData.businesses[0]?.id || 'biz-1',
					location_id: body?.location_id || mockData.locations[0]?.id || 'loc-1',
					service_id: body?.service_id || mockData.services[0]?.id || 'srv-1',
					provider_id: body?.provider_id || mockData.providers[0]?.id || 'prov-1',
					customer_id: body?.customer_id || mockData.customers[0]?.id || 'cust-1',
					starts_at: body?.starts_at || nowIso,
					ends_at: new Date(Date.now() + 3600000).toISOString(),
					price: '350.00',
					currency: 'SAR',
					status: 'confirmed',
					source: body?.source || 'direct_link',
					cancellation_reason: null,
					notes: body?.notes || null
				};
				mockData.bookings.unshift(newBooking);
				return json(newBooking);
			}

			if (subId && parts[4]) {
				const action = parts[4];
				const b = mockData.bookings.find((x) => x.id === subId);
				if (b) {
					if (action === 'check-in') b.status = 'checked_in';
					if (action === 'start') b.status = 'in_service';
					if (action === 'complete') b.status = 'completed';
					if (action === 'cancel') b.status = 'cancelled';
					if (action === 'no-show') b.status = 'no_show';
					return json(b);
				}
			}

			if (subId) {
				const b = mockData.bookings.find((x) => x.id === subId) || mockData.bookings[0];
				return json(b);
			}

			return json({ items: mockData.bookings, total: mockData.bookings.length });
		}

		// Customers
		if (section === 'customers') {
			if (method === 'POST') {
				const newCust = {
					id: 'cust-' + (mockData.customers.length + 1),
					tenant_id: tenantId,
					full_name: body?.full_name || 'Customer Name',
					phone: body?.phone || '+966500000000',
					email: body?.email || null,
					preferred_language: body?.preferred_language || 'ar',
					marketing_consent: Boolean(body?.marketing_consent),
					whatsapp_consent: Boolean(body?.whatsapp_consent),
					notes: body?.notes || null,
					created_at: nowIso,
					updated_at: nowIso
				};
				mockData.customers.unshift(newCust);
				return json(newCust);
			}
			if (subId) {
				return json(mockData.customers.find((x) => x.id === subId) || mockData.customers[0]);
			}
			return json({ items: mockData.customers, total: mockData.customers.length });
		}

		// Queues
		if (section === 'queues') {
			if (parts[3] && parts[4] === 'entries') {
				return json({ items: mockData.queue_entries, total: mockData.queue_entries.length });
			}
			if (subId === 'entries') {
				if (parts[4]) {
					const entry = mockData.queue_entries.find((x) => x.id === parts[4]);
					return json(entry || mockData.queue_entries[0]);
				}
				if (method === 'POST') {
					const newEntry = {
						id: 'qe-' + (mockData.queue_entries.length + 1),
						queue_id: body?.queue_id || mockData.queues[0].id,
						location_id: mockData.locations[0].id,
						customer_id: body?.customer_id || mockData.customers[0].id,
						service_id: body?.service_id || mockData.services[0].id,
						provider_id: body?.provider_id || null,
						status: 'waiting',
						source: 'walk_in',
						position: mockData.queue_entries.length + 1,
						party_size: body?.party_size || 1,
						booking_id: null,
						joined_at: nowIso,
						called_at: null,
						place_in_line: mockData.queue_entries.length + 1,
						estimated_wait_minutes: 15
					};
					mockData.queue_entries.push(newEntry);
					return json(newEntry);
				}
				return json({ items: mockData.queue_entries, total: mockData.queue_entries.length });
			}
			return json({ items: mockData.queues, total: mockData.queues.length });
		}

		// Analytics
		if (section === 'analytics') {
			if (subId === 'overview') {
				return json({
					business_id: 'biz-1',
					window: {
						date_from: query.date_from || '2026-08-18',
						date_to: query.date_to || '2026-09-17',
						timezone: 'Asia/Riyadh',
						days: 30
					},
					currency: 'SAR',
					excluded_rows: 0,
					kpis: [
						{
							metric: 'revenue',
							value: '48500.00',
							unit: 'SAR',
							sample_size: 142,
							suppressed: false
						},
						{
							metric: 'bookings',
							value: '142',
							unit: 'count',
							sample_size: 142,
							suppressed: false
						},
						{
							metric: 'average_ticket',
							value: '341.55',
							unit: 'SAR',
							sample_size: 142,
							suppressed: false
						},
						{ metric: 'utilization', value: '82.4', unit: '%', sample_size: 142, suppressed: false }
					]
				});
			}

			if (subId === 'charts') {
				const chartCatalog = [
					{
						chart_id: 'revenue_trend',
						kind: 'combo',
						title_en: 'Revenue & Bookings Trend',
						title_ar: 'اتجاه الإيرادات والحجوزات',
						question_en: 'How is daily revenue trending over the selected period?',
						question_ar: 'كيف يتجه الإيراد اليومي عبر الفترة المحددة؟',
						required_feature: 'view_analytics'
					},
					{
						chart_id: 'service_mix',
						kind: 'donut',
						title_en: 'Service Revenue Mix',
						title_ar: 'توزيع إيرادات الخدمات',
						question_en: 'Which service categories generate the most revenue?',
						question_ar: 'أي فئات الخدمات تحقق أعلى إيراد؟',
						required_feature: 'view_analytics'
					}
				];
				if (parts[3]) {
					// Detail of specific chart
					const chartId = parts[3];
					return json({
						chart_id: chartId,
						kind: chartId === 'service_mix' ? 'donut' : 'combo',
						title: chartId === 'service_mix' ? 'Service Revenue Mix' : 'Revenue Trend',
						description: 'Visual performance metrics for business operations',
						locale: 'en',
						business_id: 'biz-1',
						date_from: query.date_from || '2026-08-18',
						date_to: query.date_to || '2026-09-17',
						granularity: 'day',
						currency: 'SAR',
						data_points: 30,
						generated_at: nowIso,
						figure: {
							data: [
								{
									x: [
										'2026-09-10',
										'2026-09-11',
										'2026-09-12',
										'2026-09-13',
										'2026-09-14',
										'2026-09-15',
										'2026-09-16'
									],
									y: [1200, 1850, 2400, 3100, 2800, 3400, 4200],
									type: 'bar',
									name: 'Revenue (SAR)'
								}
							],
							layout: { title: 'Daily Revenue' }
						}
					});
				}
				return json(chartCatalog);
			}

			if (subId === 'breakdown') {
				return json({
					dimension: query.dimension || 'service',
					rows: [
						{
							dimension: query.dimension || 'service',
							key: 'srv-1',
							label: 'HydraFacial Glow Treatment',
							label_en: 'HydraFacial Glow Treatment',
							label_ar: 'جلسة هيدرافيشل لنضارة البشرة',
							bookings: 54,
							completed: 52,
							revenue: '23400.00',
							share_of_revenue: '48.2'
						},
						{
							dimension: query.dimension || 'service',
							key: 'srv-2',
							label: 'Royal Moroccan Bath & Ritual',
							label_en: 'Royal Moroccan Bath & Ritual',
							label_ar: 'حمام مغربي ملكي وطقوس استرخاء',
							bookings: 42,
							completed: 41,
							revenue: '15580.00',
							share_of_revenue: '32.1'
						},
						{
							dimension: query.dimension || 'service',
							key: 'srv-3',
							label: 'Signature Haircut & Blowout',
							label_en: 'Signature Haircut & Blowout',
							label_ar: 'قص شعر وتصفيف احترافي',
							bookings: 46,
							completed: 45,
							revenue: '9520.00',
							share_of_revenue: '19.7'
						}
					]
				});
			}

			if (subId === 'forecast') {
				return json({
					business_id: 'biz-1',
					metric: query.metric || 'revenue',
					currency: 'SAR',
					method: 'linear_trend',
					history_weeks: 8,
					slope_per_week: '1250.00',
					points: [
						{
							week_start: '2026-09-20',
							value: '13500.00',
							lower: '12000.00',
							upper: '15000.00',
							is_forecast: true
						},
						{
							week_start: '2026-09-27',
							value: '14750.00',
							lower: '13000.00',
							upper: '16500.00',
							is_forecast: true
						}
					]
				});
			}

			if (subId === 'financial-summary') {
				return json({
					business_id: 'biz-1',
					window: {
						date_from: '2026-08-18',
						date_to: '2026-09-17',
						timezone: 'Asia/Riyadh',
						days: 30
					},
					currency: 'SAR',
					revenue: '48500.00',
					collected: '47200.00',
					refunded: '450.00',
					commission_accrued: '3880.00',
					commission_reversed: '0.00',
					payouts_collected: '47200.00',
					payouts_processing_fees: '1038.40',
					payouts_commission_netted: '3880.00',
					payouts_net: '42281.60',
					invoiced_subscription: '499.00',
					invoiced_commission: '3880.00',
					invoiced_processing: '1038.40',
					invoiced_vat: '812.61',
					invoiced_total: '6230.01',
					outstanding_invoices: 0,
					outstanding_total: '0.00'
				});
			}
		}

		// Billing
		if (section === 'billing') {
			if (subId === 'plans') {
				return json(mockData.plans);
			}
			if (subId === 'subscriptions') {
				if (parts[3]) {
					return json(mockData.subscription);
				}
				return json(mockData.subscription);
			}
			if (subId === 'invoices') {
				return json({
					items: [
						{
							id: 'inv-1',
							business_id: 'biz-1',
							period_start: '2026-08-01T00:00:00Z',
							period_end: '2026-08-31T23:59:59Z',
							status: 'paid',
							subscription_amount: '499.00',
							commission_amount: '3200.00',
							processing_amount: '890.00',
							vat_amount: '688.35',
							total_amount: '5277.35',
							currency: 'SAR',
							issued_at: '2026-09-01T00:00:00Z',
							due_at: '2026-09-15T00:00:00Z',
							paid_at: '2026-09-05T12:00:00Z',
							lines_url: `/tenants/${tenantId}/billing/invoices/inv-1/lines`
						}
					],
					total: 1
				});
			}
			if (subId === 'payouts') {
				return json({
					items: [
						{
							id: 'pay-1',
							business_id: 'biz-1',
							payout_date: '2026-09-16',
							collected_amount: '4200.00',
							processing_fee: '92.40',
							commission_netted: '336.00',
							net_amount: '3771.60',
							currency: 'SAR',
							booking_ids: ['bk-1', 'bk-2'],
							paid_at: '2026-09-16T18:00:00Z'
						}
					],
					total: 1
				});
			}
		}

		// Memberships
		if (section === 'memberships') {
			return json({ items: mockData.memberships, total: mockData.memberships.length });
		}

		// AI Agents
		if (section === 'ai') {
			if (subId === 'agents') {
				return json({
					available: ['concierge_agent', 'analyst_agent'],
					aliases: {},
					agents: [
						{
							name: 'concierge_agent',
							audience: 'customer',
							goal: 'Assists customers in Arabic and English with service recommendations and booking availability',
							required_feature: null
						},
						{
							name: 'analyst_agent',
							audience: 'staff',
							goal: 'Provides business owners and managers with instant analytical insights on revenue and retention',
							required_feature: 'view_analytics'
						}
					]
				});
			}
			if (subId === 'chat') {
				const userMsg = body?.message || '';
				return json({
					session_id: body?.session_id || 'sess-1',
					agent: query.agent || 'concierge_agent',
					reply: `مرحباً بك! أنا مساعد NOVA الذكي. يسعدني مساعدتك في استفسارك بخصوص: "${userMsg}". جميع خدماتنا وحجوزاتنا جاهزة لك!`,
					suggested_actions: ['View availability', 'Check top services', 'Review queue status'],
					requires_human_handoff: false,
					related_booking_id: null,
					related_ticket_url: null,
					held_slots: [],
					queue_places: [],
					pending_cancellations: [],
					degraded: false,
					confidence: 0.95,
					metrics_used: ['daily_revenue', 'utilization_rate'],
					charts: [],
					proposed_actions: []
				});
			}
		}
	}

	return json(
		{ error: { code: 'not_found', message: `Route /${path} not found.` } },
		{ status: 404 }
	);
}

export const GET = ({ request, params, url }) => handleRequest(request, params, url, 'GET');
export const POST = ({ request, params, url }) => handleRequest(request, params, url, 'POST');
export const PUT = ({ request, params, url }) => handleRequest(request, params, url, 'PUT');
export const PATCH = ({ request, params, url }) => handleRequest(request, params, url, 'PATCH');
export const DELETE = ({ request, params, url }) => handleRequest(request, params, url, 'DELETE');
export const OPTIONS = () => new Response(null, { status: 204 });
