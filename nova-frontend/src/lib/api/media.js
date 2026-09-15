/**
 * media — nova_backend/app/modules/media/router.py
 *
 * Nextcloud-backed asset metadata. There is no endpoint here that accepts a
 * file body — the browser PUTs the bytes straight to Nextcloud with a
 * short-lived authorisation this API issues, so `uploadMediaFile` below talks
 * to `upload_url` directly rather than going through `http`/`API_ROOT`.
 */
import { http, tenantPath } from './client.js';

/**
 * @typedef {'logo'|'cover'|'portfolio'|'provider_photo'} MediaAssetKind
 */

/**
 * @typedef {Object} MediaUploadAuthorisation
 * @property {string} asset_id
 * @property {string} upload_url Points at Nextcloud, not this API.
 * @property {string} webdav_path
 * @property {string} upload_token
 * @property {string} expires_at
 */

/**
 * @typedef {Object} MediaAsset
 * @property {string} id
 * @property {string} business_id
 * @property {string|null} location_id
 * @property {MediaAssetKind} kind
 * @property {string} file_name
 * @property {string} content_type
 * @property {number} size_bytes
 * @property {boolean} is_ready
 * @property {boolean} is_public
 * @property {string} created_at
 */

/**
 * @typedef {Object} MediaLink
 * @property {string} asset_id
 * @property {string} url
 */

/**
 * Authorises one upload to one path. Staff only — this reserves storage.
 * @param {string} tenantId
 * @param {{ businessId: string, locationId?: string|null, kind: MediaAssetKind,
 *   fileName: string, contentType: string, sizeBytes: number }} params
 * @returns {Promise<MediaUploadAuthorisation>}
 */
export function requestMediaUpload(
	tenantId,
	{ businessId, locationId = null, kind, fileName, contentType, sizeBytes }
) {
	return http.post(tenantPath(tenantId, '/media/uploads'), {
		business_id: businessId,
		location_id: locationId,
		kind,
		file_name: fileName,
		content_type: contentType,
		size_bytes: sizeBytes
	});
}

/**
 * Puts the file straight to Nextcloud's `upload_url` — never through `/api/v1`.
 * @param {MediaUploadAuthorisation} authorisation
 * @param {File|Blob} file
 */
export async function uploadMediaFile(authorisation, file) {
	const response = await fetch(authorisation.upload_url, {
		method: 'PUT',
		headers: { 'Content-Type': file.type || 'application/octet-stream' },
		body: file
	});
	if (!response.ok) {
		throw new Error(`Upload to storage failed with status ${response.status}.`);
	}
}

/** Confirms the bytes landed, and makes the asset renderable. @returns {Promise<MediaAsset>} */
export function completeMediaUpload(tenantId, assetId, uploadToken) {
	return http.post(tenantPath(tenantId, `/media/uploads/${assetId}/complete`), {
		upload_token: uploadToken
	});
}

/**
 * Convenience wrapper: authorise, PUT the bytes, then confirm.
 * @param {string} tenantId
 * @param {{ businessId: string, locationId?: string|null, kind: MediaAssetKind, file: File }} params
 * @returns {Promise<MediaAsset>}
 */
export async function uploadMediaAsset(tenantId, { businessId, locationId = null, kind, file }) {
	const authorisation = await requestMediaUpload(tenantId, {
		businessId,
		locationId,
		kind,
		fileName: file.name,
		contentType: file.type || 'application/octet-stream',
		sizeBytes: file.size
	});
	await uploadMediaFile(authorisation, file);
	return completeMediaUpload(tenantId, authorisation.asset_id, authorisation.upload_token);
}

/** @returns {Promise<{ items: MediaAsset[] }>} */
export function listBusinessMedia(tenantId, businessId, { kind = null, limit = 20, offset = 0 } = {}) {
	return http.get(tenantPath(tenantId, '/media'), {
		query: { business_id: businessId, kind, limit, offset }
	});
}

/** @returns {Promise<MediaAsset>} */
export function getMediaAsset(tenantId, assetId) {
	return http.get(tenantPath(tenantId, `/media/${assetId}`));
}

/** A shareable URL, generated fresh on every call. @returns {Promise<MediaLink>} */
export function getMediaLink(tenantId, assetId) {
	return http.get(tenantPath(tenantId, `/media/${assetId}/link`));
}

/** Soft delete — the worker removes the binary afterwards. */
export function deleteMediaAsset(tenantId, assetId) {
	return http.delete(tenantPath(tenantId, `/media/${assetId}`));
}
