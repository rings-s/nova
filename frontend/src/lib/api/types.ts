// Mirrors backend/app/modules/tenants/schemas.py — keep in sync by hand until
// an OpenAPI-generated client is worth the setup cost for this project's size.

export interface TenantRead {
	id: string;
	name_en: string;
	name_ar: string;
	slug: string;
	phone: string;
	default_currency: string;
	created_at: string;
	updated_at: string;
}

export interface BranchRead {
	id: string;
	tenant_id: string;
	name_en: string;
	name_ar: string;
	slug: string;
	phone: string;
	timezone: string;
	created_at: string;
	updated_at: string;
}

export interface HealthStatus {
	status: 'ok' | string;
}
