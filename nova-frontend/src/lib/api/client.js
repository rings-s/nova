/**
 * Core HTTP client for the NOVA FastAPI backend.
 *
 * Every module under `$lib/api` calls through `http` here rather than raw
 * `fetch`, so auth headers, tenant paths, idempotency keys and the backend's
 * error envelope (`{"error": {code, message, field, retryable, correlation_id}}`,
 * see nova_backend/app/core/schemas.py) are handled in exactly one place.
 */
import { PUBLIC_API_BASE_URL } from '$env/static/public';

const API_ORIGIN = (
	PUBLIC_API_BASE_URL && PUBLIC_API_BASE_URL.trim() !== '' ? PUBLIC_API_BASE_URL : ''
).replace(/\/+$/, '');
export const API_ROOT = `${API_ORIGIN}/api/v1`;

export const CORRELATION_ID_HEADER = 'X-Correlation-ID';

/** Mirrors `ErrorDetail` in nova_backend/app/core/schemas.py. */
export class ApiError extends Error {
	/**
	 * @param {{ status: number, code: string, message: string, field?: string|null,
	 *   retryable?: boolean, correlationId?: string|null }} init
	 */
	constructor({ status, code, message, field = null, retryable = false, correlationId = null }) {
		super(message);
		this.name = 'ApiError';
		this.status = status;
		this.code = code;
		this.field = field;
		this.retryable = retryable;
		this.correlationId = correlationId;
	}
}

/** The request never reached the server: offline, DNS, CORS, timeout. */
export class NetworkError extends Error {
	/** @param {unknown} cause */
	constructor(cause) {
		super('Could not reach the server. Check your connection and try again.');
		this.name = 'NetworkError';
		this.cause = cause;
	}
}

/**
 * Wired up by `$lib/stores/auth.svelte.js` at app startup, so this module
 * never imports the auth store directly (that would be circular: the store
 * calls the API, the API would call the store).
 * @type {{ getAccessToken: () => string|null, refresh: () => Promise<unknown>, onUnauthorized: () => void }}
 */
let auth = {
	getAccessToken: () => null,
	refresh: async () => {
		throw new Error('Auth is not configured yet.');
	},
	onUnauthorized: () => {}
};

/** @param {Partial<typeof auth>} handlers */
export function configureAuth(handlers) {
	auth = { ...auth, ...handlers };
}

/** @param {Record<string, unknown>|undefined} params */
function buildQuery(params) {
	if (!params) return '';
	const search = new URLSearchParams();
	for (const [key, value] of Object.entries(params)) {
		if (value === undefined || value === null || value === '') continue;
		if (Array.isArray(value)) {
			for (const item of value) search.append(key, String(item));
		} else if (value instanceof Date) {
			search.set(key, value.toISOString());
		} else {
			search.set(key, String(value));
		}
	}
	const qs = search.toString();
	return qs ? `?${qs}` : '';
}

/**
 * @typedef {Object} RequestOptions
 * @property {string} [method]
 * @property {unknown} [body]
 * @property {Record<string, unknown>} [query]
 * @property {Record<string, string>} [headers]
 * @property {string} [idempotencyKey]
 * @property {AbortSignal} [signal]
 * @property {boolean} [skipAuth] Skip attaching/refreshing the bearer token —
 *   for /auth/* itself, and for discovery's public reads.
 * @property {boolean} [_retried] Internal: set on the one automatic retry after a refresh.
 */

/** @param {string} path @param {RequestOptions} options */
async function performFetch(path, options) {
	const { method = 'GET', body, query, headers = {}, idempotencyKey, signal, skipAuth } = options;
	const url = `${API_ROOT}${path}${buildQuery(query)}`;
	const requestHeaders = new Headers(headers);
	if (body !== undefined) requestHeaders.set('Content-Type', 'application/json');
	if (idempotencyKey) requestHeaders.set('Idempotency-Key', idempotencyKey);

	if (!skipAuth) {
		const token = auth.getAccessToken();
		if (token) requestHeaders.set('Authorization', `Bearer ${token}`);
	}

	try {
		return await fetch(url, {
			method,
			headers: requestHeaders,
			body: body !== undefined ? JSON.stringify(body) : undefined,
			signal
		});
	} catch (cause) {
		throw new NetworkError(cause);
	}
}

/**
 * Retries exactly once, after a token refresh, on a 401 — never for
 * `/auth/*` itself or discovery's public reads (`skipAuth`), and never twice.
 * @param {string} path @param {RequestOptions} options
 */
async function requestWithAuthRetry(path, options) {
	const response = await performFetch(path, options);
	if (response.status !== 401 || options.skipAuth || options._retried) {
		return response;
	}
	try {
		await auth.refresh();
	} catch {
		auth.onUnauthorized();
		return response;
	}
	return performFetch(path, { ...options, _retried: true });
}

/** @param {Response} response @returns {Promise<{ code?: string, message?: string, field?: string|null, retryable?: boolean, correlation_id?: string|null }|null>} */
async function parseErrorBody(response) {
	try {
		const parsed = await response.json();
		return parsed?.error ?? null;
	} catch {
		return null;
	}
}

/**
 * @param {string} path Path under `/api/v1`, e.g. `/tenants/{id}/bookings`.
 * @param {RequestOptions} [options]
 */
export async function apiFetch(path, options = {}) {
	const response = await requestWithAuthRetry(path, options);
	const correlationId = response.headers.get(CORRELATION_ID_HEADER);

	if (response.status === 204) return null;

	if (!response.ok) {
		if (response.status === 401 && !options.skipAuth) {
			auth.onUnauthorized();
		}
		const errorBody = await parseErrorBody(response);
		throw new ApiError({
			status: response.status,
			code: errorBody?.code ?? 'unknown_error',
			message: errorBody?.message ?? `Request failed with status ${response.status}.`,
			field: errorBody?.field ?? null,
			retryable: errorBody?.retryable ?? response.status === 429,
			correlationId: errorBody?.correlation_id ?? correlationId
		});
	}

	const text = await response.text();
	return text ? JSON.parse(text) : null;
}

/** Thin verb helpers so module files read as `http.get(path)` / `http.post(path, body)`. */
export const http = {
	/** @param {string} path @param {Omit<RequestOptions, 'method' | 'body'>} [options] */
	get: (path, options) => apiFetch(path, { ...options, method: 'GET' }),
	/** @param {string} path @param {unknown} [body] @param {Omit<RequestOptions, 'method' | 'body'>} [options] */
	post: (path, body, options) => apiFetch(path, { ...options, method: 'POST', body }),
	/** @param {string} path @param {unknown} [body] @param {Omit<RequestOptions, 'method' | 'body'>} [options] */
	put: (path, body, options) => apiFetch(path, { ...options, method: 'PUT', body }),
	/** @param {string} path @param {unknown} [body] @param {Omit<RequestOptions, 'method' | 'body'>} [options] */
	patch: (path, body, options) => apiFetch(path, { ...options, method: 'PATCH', body }),
	/** @param {string} path @param {Omit<RequestOptions, 'method' | 'body'>} [options] */
	delete: (path, options) => apiFetch(path, { ...options, method: 'DELETE' })
};

/**
 * Every tenant-scoped route hangs off this — `tenantPath(id, '/bookings')`.
 * @param {string} tenantId @param {string} [suffix]
 */
export function tenantPath(tenantId, suffix = '') {
	return `/tenants/${tenantId}${suffix}`;
}
