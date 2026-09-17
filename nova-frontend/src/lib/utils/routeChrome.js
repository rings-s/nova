/**
 * Whether a pathname gets the redesigned public/marketing chrome (header nav
 * links + footer) rather than today's plain app-shell chrome. The staff
 * dashboard (`/app`) and the Playwright e2e harness (`/demo`) must render
 * exactly as they did before this redesign, so both are excluded here rather
 * than duplicating this check ad hoc in every layout/component that needs it.
 *
 * @param {string} pathname
 */
export function isPublicChromeRoute(pathname) {
	return !pathname.startsWith('/app') && !pathname.startsWith('/demo');
}
