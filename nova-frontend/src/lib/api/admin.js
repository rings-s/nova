/**
 * admin — nova_backend/app/modules/catalog/router.py (`admin_router`) and
 * nova_backend/app/modules/admin/router.py (the platform console, below)
 *
 * What every business on NOVA shares, edited by a NOVA administrator
 * (`users.is_superuser`) and nobody else, whatever their role in a salon. The
 * backend refuses anyone else with 403 `forbidden`.
 */
import { http } from './client.js';

/**
 * @typedef {import('./catalog.js').Category & {
 *   is_active: boolean, created_at: string, updated_at: string
 * }} AdminCategory
 */

/** Every category, retired ones included. @returns {Promise<AdminCategory[]>} */
export function listAllCategories() {
	return http.get('/admin/catalog/categories');
}

/**
 * Its slug comes from the English name and never changes.
 * @param {{ nameEn: string, nameAr: string }} params @returns {Promise<AdminCategory>}
 */
export function createCategory({ nameEn, nameAr }) {
	return http.post('/admin/catalog/categories', { name_en: nameEn, name_ar: nameAr });
}

/**
 * Renames a category, or retires or restores it. Omitted fields keep their value.
 * @param {string} categoryId
 * @param {{ nameEn?: string, nameAr?: string, isActive?: boolean }} changes
 * @returns {Promise<AdminCategory>}
 */
export function updateCategory(categoryId, { nameEn, nameAr, isActive }) {
	/** @type {Record<string, unknown>} */
	const body = {};
	if (nameEn !== undefined) body.name_en = nameEn;
	if (nameAr !== undefined) body.name_ar = nameAr;
	if (isActive !== undefined) body.is_active = isActive;
	return http.patch(`/admin/catalog/categories/${categoryId}`, body);
}

// --- The platform console: nova_backend/app/modules/admin/router.py ---------
//
// Every table across every tenant, masked. Writes through each table's curated
// actions, or as direct edits (add, change, delete) to any table but the audit
// log. Every read and write is recorded in the audit log.

/**
 * @typedef {{ name: string, group: string, estimated_rows: number }} AdminTable
 * @typedef {{
 *   name: string, type: 'uuid'|'text'|'number'|'boolean'|'datetime'|'date'|'enum'|'json',
 *   nullable: boolean, primary_key: boolean, masked: boolean, searchable: boolean,
 *   filterable: boolean, references: string|null, choices: string[],
 *   writable: boolean, required: boolean, max_length: number|null
 * }} AdminColumn
 * @typedef {{ name: string, label: string, destructive: boolean, requires_reason: boolean }} AdminAction
 * @typedef {{
 *   name: string, group: string, editable: boolean, columns: AdminColumn[], primary_key: string[],
 *   actions: AdminAction[], related: { table: string, column: string }[]
 * }} AdminTableDetail
 * @typedef {{ id: string, tenant_id: string|null, values: Record<string, unknown>, actions: AdminAction[] }} AdminRow
 * @typedef {{ items: AdminRow[], total: number, limit: number, offset: number }} AdminRowsPage
 */

/** @returns {Promise<AdminTable[]>} */
export function listTables() {
	return http.get('/admin/tables');
}

/** @param {string} table @returns {Promise<AdminTableDetail>} */
export function describeTable(table) {
	return http.get(`/admin/tables/${encodeURIComponent(table)}`);
}

/**
 * @param {string} table
 * @param {{ q?: string, filters?: string[], orderBy?: string|null, desc?: boolean, limit?: number, offset?: number }} [params]
 *   `filters` are `column:value` pairs, each an exact match.
 * @returns {Promise<AdminRowsPage>}
 */
export function listRows(table, { q, filters = [], orderBy, desc, limit = 50, offset = 0 } = {}) {
	const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
	if (q) query.set('q', q);
	if (orderBy) query.set('order_by', orderBy);
	if (desc) query.set('desc', 'true');
	for (const filter of filters) query.append('filter', filter);
	return http.get(`/admin/tables/${encodeURIComponent(table)}/rows?${query}`);
}

/** @param {string} table @param {string} rowId @returns {Promise<AdminRow>} */
export function getRow(table, rowId) {
	return http.get(`/admin/tables/${encodeURIComponent(table)}/rows/${encodeURIComponent(rowId)}`);
}

/**
 * @param {string} table @param {string} rowId @param {string} action
 * @param {{ reason?: string|null }} [body]
 * @returns {Promise<AdminRow>}
 */
export function runAction(table, rowId, action, { reason = null } = {}) {
	return http.post(
		`/admin/tables/${encodeURIComponent(table)}/rows/${encodeURIComponent(rowId)}/actions/${encodeURIComponent(action)}`,
		{ reason }
	);
}

// Direct edits: only the database's own constraints apply, not the owning
// module's rules, and no event is published (no notification is sent).

/**
 * A column left out takes its default.
 * @param {string} table @param {Record<string, unknown>} values
 * @returns {Promise<AdminRow>}
 */
export function createRow(table, values) {
	return http.post(`/admin/tables/${encodeURIComponent(table)}/rows`, { values });
}

/**
 * Send only what changes, and never a masked value back.
 * @param {string} table @param {string} rowId @param {Record<string, unknown>} values
 * @returns {Promise<AdminRow>}
 */
export function updateRow(table, rowId, values) {
	return http.patch(
		`/admin/tables/${encodeURIComponent(table)}/rows/${encodeURIComponent(rowId)}`,
		{ values }
	);
}

/**
 * 409 while other rows still point at it.
 * @param {string} table @param {string} rowId @returns {Promise<void>}
 */
export function deleteRow(table, rowId) {
	return http.delete(
		`/admin/tables/${encodeURIComponent(table)}/rows/${encodeURIComponent(rowId)}`
	);
}
