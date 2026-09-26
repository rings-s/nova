/**
 * Arabic for every message in the app, keyed by its English text (see
 * `index.svelte.js`). Split by area only to keep each file readable; a key
 * may appear in more than one section, and the later one wins.
 *
 * A plural message maps to `{ zero, one, two, few, many, other }`, the
 * `Intl.PluralRules` categories for Arabic, under the English plural form.
 */
import { COMMON } from './ar/common.js';
import { ERRORS } from './ar/errors.js';
import { LAYOUT } from './ar/layout.js';
import { MARKETING } from './ar/marketing.js';
import { CUSTOMER } from './ar/customer.js';
import { DASHBOARD } from './ar/dashboard.js';

/** @type {Record<string, string | Partial<Record<Intl.LDMLPluralRule, string>>>} */
export const AR = {
	...COMMON,
	...ERRORS,
	...LAYOUT,
	...MARKETING,
	...CUSTOMER,
	...DASHBOARD
};
