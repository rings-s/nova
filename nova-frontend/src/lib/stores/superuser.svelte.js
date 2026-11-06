/**
 * Whether the signed-in account is a NOVA administrator (`users.is_superuser`).
 * The token does not say, so this asks `GET /auth/me`, once per account.
 *
 * It only decides whether to *show* the way to `/admin`; every `/admin` route
 * checks for itself (`require_superuser`).
 */
import { me } from '../api/auth.js';

let isSuperuser = $state(false);
/** @type {string|null} */
let loadedFor = null;
/** @type {Promise<boolean>|null} */
let loading = null;

export const superuserStore = {
	get isSuperuser() {
		return isSuperuser;
	},
	/**
	 * Asks the API unless already asked for this account; callers at the same
	 * time share one request. Keyed on the user, so signing in as someone else
	 * in the same tab never keeps the previous person's answer.
	 * @param {string} userId
	 * @returns {Promise<boolean>}
	 */
	load(userId) {
		if (loadedFor === userId && loading) return loading;
		isSuperuser = false;
		loadedFor = userId;
		const request = me()
			.then((account) => {
				const answer = account?.is_superuser === true;
				if (loading === request) isSuperuser = answer;
				return answer;
			})
			.catch((err) => {
				// Fail closed, and ask again next time.
				if (loading === request) loading = null;
				throw err;
			});
		loading = request;
		return request;
	},
	clear() {
		isSuperuser = false;
		loadedFor = null;
		loading = null;
	}
};
