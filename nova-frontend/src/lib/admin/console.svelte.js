/**
 * The platform console's shared state: whether the signed-in account is a NOVA
 * administrator, and the table list for the sidebar. Loaded once by
 * `routes/admin/+layout.svelte`; the pages under it read it.
 *
 * `is_superuser` only decides what to show. Every `/admin` route checks it for
 * itself (`require_superuser`).
 */
import { me } from '$lib/api/auth.js';
import { listTables } from '$lib/api/admin.js';
import { m } from '$lib/i18n/index.svelte.js';

export const consoleState = $state({
	/** @type {'loading'|'denied'|'ready'} */
	status: 'loading',
	/** @type {import('$lib/api/admin.js').AdminTable[]} */
	tables: []
});

let loading = /** @type {Promise<void>|null} */ (null);

/** Checks the account and loads the tables, once per page load. */
export function loadConsole() {
	loading ??= me()
		.then(async (account) => {
			if (!account.is_superuser) {
				consoleState.status = 'denied';
				return;
			}
			consoleState.tables = await listTables();
			consoleState.status = 'ready';
		})
		.catch((err) => {
			consoleState.status = 'denied';
			loading = null;
			throw err;
		});
	return loading;
}

/** Forgets the check, so the next account signed in on this tab is asked again. */
export function resetConsole() {
	loading = null;
	consoleState.status = 'loading';
	consoleState.tables = [];
}

/** Sidebar order, and the label each module's group is shown under. */
export const GROUPS = /** @type {const} */ ([
	['identity', m('Accounts & tenants')],
	['catalog', m('Catalog')],
	['booking', m('Bookings')],
	['queue', m('Queue')],
	['payment', m('Payments')],
	['billing', m('Billing')],
	['review', m('Reviews')],
	['discovery', m('Marketplace')],
	['notification', m('Notifications')],
	['platform', m('Platform')]
]);

/** `membership_invites` → `Membership invites`. Table names are not translated. */
export function humanize(/** @type {string} */ name) {
	const words = name.replaceAll('_', ' ');
	return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Up to `limit` columns to show in a list, most telling first: the id, a name,
 * a status, the tenant, then a timestamp, then whatever else there is.
 * @param {import('$lib/api/admin.js').AdminColumn[]} columns
 */
export function listColumns(columns, limit = 7) {
	const rank = (/** @type {import('$lib/api/admin.js').AdminColumn} */ column) => {
		const name = column.name;
		if (column.primary_key) return 0;
		if (/^(name_en|full_name|email|slug|title_en|event_name|table_name|name)$/.test(name)) return 1;
		if (/^(status|kind|role|tier|action|is_active|is_listed)$/.test(name)) return 2;
		if (name === 'tenant_id') return 3;
		if (/^(created_at|occurred_at|starts_at|received_at)$/.test(name)) return 4;
		if (column.type === 'json' || column.masked) return 9;
		return 5;
	};
	return columns
		.map((column, index) => ({ column, index }))
		.sort((a, b) => rank(a.column) - rank(b.column) || a.index - b.index)
		.slice(0, limit)
		.map(({ column }) => column);
}
