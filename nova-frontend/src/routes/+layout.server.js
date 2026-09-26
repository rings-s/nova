/** The request's language, as `hooks.server.js` chose it. */
export function load({ locals }) {
	return { locale: locals.locale };
}
