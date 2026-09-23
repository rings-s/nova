/**
 * Global toast queue, rendered by `$lib/components/ui/ToastContainer.svelte`
 * (mount it once, in the root layout). Push from anywhere — a load function,
 * a form handler, a catch block — without threading props through the tree.
 */

/** @typedef {{ id: number, message: string, type: 'info'|'success'|'error', duration: number }} Toast */

let toasts = $state(/** @type {Toast[]} */ ([]));
let nextId = 1;
/**
 * Auto-dismiss timers by toast id. Plain bookkeeping, deliberately not
 * reactive: nothing renders from it.
 * @type {Record<number, ReturnType<typeof setTimeout>>}
 */
const timers = {};

/** @param {number} id @param {number} duration */
function schedule(id, duration) {
	clearTimeout(timers[id]);
	if (duration > 0) timers[id] = setTimeout(() => dismiss(id), duration);
}

/**
 * Adds a toast — unless the same message of the same type is already on
 * screen, in which case that one simply stays up longer. One failure often
 * surfaces from several requests at once (a page loading two lists, a lapsed
 * session hitting every call); the person needs to be told once.
 * @param {string} message @param {{ type?: Toast['type'], duration?: number }} [options]
 */
function push(message, { type = 'info', duration = 4000 } = {}) {
	const existing = toasts.find((toast) => toast.message === message && toast.type === type);
	if (existing) {
		schedule(existing.id, duration);
		return existing.id;
	}
	const id = nextId++;
	toasts = [...toasts, { id, message, type, duration }];
	schedule(id, duration);
	return id;
}

/** @param {number} id */
function dismiss(id) {
	clearTimeout(timers[id]);
	delete timers[id];
	toasts = toasts.filter((toast) => toast.id !== id);
}

/**
 * What to tell a person about a failed request. A rejected session reads as
 * what it means for them, not as the server's diagnostic ("Malformed token.").
 * @param {unknown} error
 */
function describe(error) {
	if (error && typeof error === 'object' && 'status' in error && error.status === 401) {
		return 'Your session has expired. Please sign in again.';
	}
	return error && typeof error === 'object' && 'message' in error && error.message
		? String(error.message)
		: 'Something went wrong.';
}

export const toastStore = {
	get all() {
		return toasts;
	},
	push,
	dismiss,
	/** @param {string} message @param {{ duration?: number }} [options] */
	success: (message, options) => push(message, { ...options, type: 'success' }),
	/** @param {string} message @param {{ duration?: number }} [options] */
	error: (message, options) =>
		push(message, { ...options, type: 'error', duration: options?.duration ?? 6000 }),
	/** @param {string} message @param {{ duration?: number }} [options] */
	info: (message, options) => push(message, { ...options, type: 'info' }),
	/**
	 * Pushes a message derived from a thrown error — an `ApiError`'s own
	 * message when there is one, else a generic fallback.
	 * @param {unknown} error
	 */
	fromError(error) {
		return push(describe(error), { type: 'error', duration: 6000 });
	}
};
