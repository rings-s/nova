/**
 * Where someone lands after signing in, and the safe version of "take me back
 * to where I was".
 *
 * Business staff (owner, manager, receptionist, provider) land on the
 * dashboard; customers on the public site. A `next` path — set when a signed-
 * out visitor was sent to sign in from a page that needs it — wins, but only
 * if it is a path on this site: an open redirect (`?next=https://evil.example`
 * or `//evil.example`) would let a phishing link borrow NOVA's sign-in page.
 */

/**
 * @param {{ isStaff: boolean }} auth
 * @returns {'/app'|'/'}
 */
export function landingPath(auth) {
	return auth.isStaff ? '/app' : '/';
}

/**
 * The `next` path if it is safe to follow, else null.
 * @param {string|null|undefined} raw
 * @returns {string|null}
 */
export function safeNext(raw) {
	if (!raw) return null;
	// Must be a same-site absolute path: "/…" but not "//…" (protocol-relative)
	// or "/\\…" (which some browsers also read as another host).
	if (!raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/\\')) return null;
	// Never bounce back to the sign-in screens themselves.
	if (/^\/(login|register)(\/|\?|$)/.test(raw)) return null;
	return raw;
}

/**
 * Where to go after signing in: `next` if safe and allowed for this account,
 * otherwise the account's landing page. A customer asked to return to a
 * dashboard page lands on the public site instead of bouncing off /app.
 * @param {{ isStaff: boolean }} auth
 * @param {string|null|undefined} next
 * @returns {string}
 */
export function afterSignIn(auth, next) {
	const target = safeNext(next);
	if (target && (auth.isStaff || !target.startsWith('/app'))) return target;
	return landingPath(auth);
}
