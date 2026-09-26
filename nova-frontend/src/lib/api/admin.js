/**
 * admin — nova_backend/app/modules/catalog/router.py (`admin_router`)
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
