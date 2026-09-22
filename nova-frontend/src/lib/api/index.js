/**
 * Barrel for `$lib/api` — re-exports every module so a page can write
 * `import { login, createBooking } from '$lib/api'` instead of reaching into
 * each file. Reach for the specific file instead when two modules export the
 * same name (there are no clashes today, but prefer `import * as booking from
 * '$lib/api/booking.js'` if that ever changes).
 */
export * from './client.js';
export * as auth from './auth.js';
export * as identity from './identity.js';
export * as catalog from './catalog.js';
export * as discovery from './discovery.js';
export * as booking from './booking.js';
export * as queue from './queue.js';
export * as payment from './payment.js';
export * as billing from './billing.js';
export * as analytics from './analytics.js';
export * as media from './media.js';
export * as notification from './notification.js';
export * as review from './review.js';
export * as ai from './ai.js';
