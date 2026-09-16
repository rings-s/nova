/**
 * Global toast queue, rendered by `$lib/components/ui/ToastContainer.svelte`
 * (mount it once, in the root layout). Push from anywhere — a load function,
 * a form handler, a catch block — without threading props through the tree.
 */

/** @typedef {{ id: number, message: string, type: 'info'|'success'|'error', duration: number }} Toast */

let toasts = $state(/** @type {Toast[]} */ ([]));
let nextId = 1;

/** @param {string} message @param {{ type?: Toast['type'], duration?: number }} [options] */
function push(message, { type = 'info', duration = 4000 } = {}) {
	const id = nextId++;
	toasts = [...toasts, { id, message, type, duration }];
	if (duration > 0) {
		setTimeout(() => dismiss(id), duration);
	}
	return id;
}

/** @param {number} id */
function dismiss(id) {
	toasts = toasts.filter((toast) => toast.id !== id);
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
		const message =
			error && typeof error === 'object' && 'message' in error
				? String(error.message)
				: 'Something went wrong.';
		return push(message, { type: 'error', duration: 6000 });
	}
};
