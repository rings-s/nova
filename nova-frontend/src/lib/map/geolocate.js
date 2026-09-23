/**
 * Finding where the device is, so an owner can drop a branch pin on it.
 *
 * A thin, careful layer over the browser's Geolocation API. It knows nothing
 * about Svelte or Leaflet and takes the geolocation object as a parameter, so
 * it is tested without a browser.
 *
 * Two things it does that a bare `getCurrentPosition` does not:
 *
 * - It reports how accurate each fix is, and lets the caller refuse a rough one.
 *   A computer with no GPS is placed from its Wi-Fi or, failing that, its IP
 *   address, and that can be off by a whole city. A pin on a public map is not
 *   somewhere to guess.
 * - It goes for a quick answer first and then a precise one. A cached or
 *   network-derived fix comes back in seconds; a GPS fix, where there is GPS,
 *   takes longer and only ever improves on it.
 */

/** @typedef {{ latitude: number, longitude: number, accuracy: number }} Fix */
/** @typedef {'unsupported'|'insecure'|'denied'|'unavailable'|'timeout'|'cancelled'} LocateFailure */

/** Stop refining once a fix is this good, in metres. Good enough to stand at a door. */
export const PRECISE_ENOUGH_M = 30;

/**
 * A fix worse than this, in metres, is not trusted with a pin: it can be the
 * wrong neighbourhood, or the wrong city. The map still moves there, and the
 * owner is asked to click the exact spot.
 */
export const PIN_WORTHY_M = 1000;

export class LocateError extends Error {
	/** @param {LocateFailure} kind @param {string} [detail] What the browser itself said. */
	constructor(kind, detail = '') {
		super(kind);
		this.name = 'LocateError';
		this.kind = kind;
		this.detail = detail;
	}
}

/**
 * The browser's error, as ours. Codes are the Geolocation spec's: 1 the user or
 * the browser said no, 2 no position could be found, 3 it took too long.
 * @param {unknown} error
 * @returns {LocateError}
 */
function toLocateError(error) {
	if (error instanceof LocateError) return error;
	const { code, message } = /** @type {{ code?: number, message?: unknown }} */ (error ?? {});
	const detail = typeof message === 'string' ? message : '';
	if (code === 1) return new LocateError('denied', detail);
	if (code === 3) return new LocateError('timeout', detail);
	return new LocateError('unavailable', detail);
}

/**
 * @param {{ coords: { latitude: number, longitude: number, accuracy: number } }} position
 * @returns {Fix}
 */
function toFix({ coords }) {
	const accuracy = Number(coords.accuracy);
	return {
		latitude: coords.latitude,
		longitude: coords.longitude,
		// Never zero, which would draw as nothing. An accuracy that is missing is
		// treated as very rough rather than very good.
		accuracy: Number.isFinite(accuracy) ? Math.max(accuracy, 1) : 100_000
	};
}

/**
 * @param {Geolocation} geolocation
 * @param {PositionOptions} options
 * @param {AbortSignal | undefined} signal
 * @returns {Promise<GeolocationPosition>}
 */
function currentPosition(geolocation, options, signal) {
	return new Promise((resolve, reject) => {
		if (signal?.aborted) return reject(new LocateError('cancelled'));
		const onabort = () => reject(new LocateError('cancelled'));
		signal?.addEventListener('abort', onabort, { once: true });
		geolocation.getCurrentPosition(
			(position) => {
				signal?.removeEventListener('abort', onabort);
				resolve(position);
			},
			(error) => {
				signal?.removeEventListener('abort', onabort);
				reject(error);
			},
			options
		);
	});
}

/**
 * Watches for better fixes until one is precise, the window closes, or the
 * caller aborts. Resolves either way; the fixes arrive through `consider`.
 * @param {Geolocation} geolocation
 * @param {(position: GeolocationPosition) => Fix} consider Returns the best fix so far.
 * @param {(error: unknown) => LocateError} remember
 * @param {() => boolean} haveFix
 * @param {{ windowMs: number, signal: AbortSignal | undefined, preciseEnoughM: number }} options
 * @returns {Promise<void>}
 */
function refine(geolocation, consider, remember, haveFix, { windowMs, signal, preciseEnoughM }) {
	return new Promise((resolve) => {
		let done = false;
		/** @type {number | null} */
		let watchId = null;
		const finish = () => {
			if (done) return;
			done = true;
			clearTimeout(timer);
			signal?.removeEventListener('abort', finish);
			if (watchId !== null) geolocation.clearWatch(watchId);
			resolve();
		};
		const timer = setTimeout(finish, windowMs);
		signal?.addEventListener('abort', finish, { once: true });

		watchId = geolocation.watchPosition(
			(position) => {
				if (consider(position).accuracy <= preciseEnoughM) finish();
			},
			(error) => {
				const failure = remember(error);
				// Nothing found yet and the provider says it cannot: waiting out the
				// window would only delay the answer. Once there is a fix, a later
				// hiccup does not matter; keep waiting for a better one.
				if (failure.kind === 'denied' || !haveFix()) finish();
			},
			{ enableHighAccuracy: true, maximumAge: 0, timeout: windowMs }
		);
		// A provider may answer before `watchPosition` has returned its id.
		if (done) geolocation.clearWatch(watchId);
		else if (signal?.aborted) finish();
	});
}

/**
 * Finds the device: a quick fix first, then a watch for a more precise one.
 * `onfix` is called for the first fix and again for each one that is better;
 * the promise resolves with the best when the search ends. Rejects with a
 * `LocateError` only when there was never a fix.
 *
 * @param {{
 *   onfix: (fix: Fix) => void,
 *   signal?: AbortSignal,
 *   geolocation?: Geolocation,
 *   secure?: boolean,
 *   quickTimeoutMs?: number,
 *   refineMs?: number,
 *   preciseEnoughM?: number
 * }} options `preciseEnoughM` ends the search early once a fix is this
 *   good (default `PRECISE_ENOUGH_M`); a caller that needs less than a door's
 *   precision — "which salons are near" — can stop sooner. `geolocation` and `secure` default to the browser's own; they are
 *   parameters so a test can supply a scripted provider.
 * @returns {Promise<Fix>}
 */
export async function locate(options) {
	// 15 s to answer, then 12 s to sharpen it: 27 s at worst, inside the "half a
	// minute" the owner is told to expect.
	const {
		onfix,
		signal,
		quickTimeoutMs = 15_000,
		refineMs = 12_000,
		preciseEnoughM = PRECISE_ENOUGH_M
	} = options;
	const geolocation = options.geolocation ?? globalThis.navigator?.geolocation;
	const secure = options.secure ?? globalThis.window?.isSecureContext ?? true;

	if (!geolocation) throw new LocateError('unsupported');
	if (!secure) throw new LocateError('insecure');
	if (signal?.aborted) throw new LocateError('cancelled');

	/** @type {Fix | null} */
	let best = null;
	/** @type {LocateError | null} */
	let firstFailure = null;

	/** Only ever improves: a later, worse fix is dropped. @param {GeolocationPosition} position */
	const consider = (position) => {
		const fix = toFix(position);
		if (!best || fix.accuracy < best.accuracy) {
			best = fix;
			onfix(fix);
		}
		return best;
	};
	/**
	 * Keeps the first failure, which is the most telling if nothing works, and
	 * returns this one, which is what the caller has to react to.
	 * @param {unknown} error
	 */
	const remember = (error) => {
		const failure = toLocateError(error);
		firstFailure ??= failure;
		return failure;
	};

	// Quick: tolerate a fix a minute old, and do not insist on GPS.
	try {
		consider(
			await currentPosition(
				geolocation,
				{ enableHighAccuracy: false, maximumAge: 60_000, timeout: quickTimeoutMs },
				signal
			)
		);
	} catch (error) {
		const failure = remember(error);
		if (failure.kind === 'denied' || failure.kind === 'cancelled') throw failure;
	}
	if (best && /** @type {Fix} */ (best).accuracy <= preciseEnoughM) return best;

	// Precise: where there is a GPS, this is where it answers.
	await refine(geolocation, consider, remember, () => best !== null, {
		windowMs: refineMs,
		signal,
		preciseEnoughM
	});

	if (best) return best;
	throw signal?.aborted
		? new LocateError('cancelled')
		: (firstFailure ?? new LocateError('unavailable'));
}

/**
 * "12 m", "850 m", "3.4 km", "40 km".
 * @param {number} metres
 */
export function describeAccuracy(metres) {
	if (metres < 1000) return `${Math.round(metres)} m`;
	const km = metres / 1000;
	return `${km < 10 ? km.toFixed(1) : Math.round(km)} km`;
}

/**
 * What to tell the owner about a fix.
 * @param {Fix} fix
 * @returns {{ tone: 'success' | 'warning', text: string, pin: boolean }}
 */
export function explainFix(fix) {
	const within = describeAccuracy(fix.accuracy);
	if (fix.accuracy <= PRECISE_ENOUGH_M) {
		return {
			tone: 'success',
			pin: true,
			text: `Located you to within about ${within}. Drag the pin if it is not exactly at your branch.`
		};
	}
	if (fix.accuracy <= PIN_WORTHY_M) {
		return {
			tone: 'success',
			pin: true,
			text: `Located you to within about ${within}, which is approximate. Zoom in and drag the pin to your branch.`
		};
	}
	return {
		tone: 'warning',
		pin: false,
		text: `Your device could only place you within about ${within}, which is too rough for a pin, so none was placed. Zoom in and click your branch on the map.`
	};
}

/**
 * What to tell the owner when there was no fix at all, and what to try instead.
 * @param {LocateError} error
 * @param {{ origin?: string, linux?: boolean }} [context] `linux` adds the hint that
 *   matters there: browsers lean on a system service that is often switched off.
 * @returns {string}
 */
export function explainLocateError(error, { origin = '', linux = false } = {}) {
	const instead = 'Click the map, paste coordinates, or type your city instead.';
	switch (error.kind) {
		case 'unsupported':
			return `This browser cannot share its location. ${instead}`;
		case 'insecure':
			return `Your browser only shares your location with secure pages (https, or http://localhost), and this page is at ${origin || 'an insecure address'}. ${instead}`;
		case 'denied':
			return `Location access is blocked for this site. Click the icon at the left of the address bar, set Location to Allow, and try again. ${instead}`;
		case 'timeout':
			return `Your browser did not answer in time. Try again, or ${instead.charAt(0).toLowerCase()}${instead.slice(1)}`;
		default:
			return `Your browser could not work out where you are.${
				linux
					? ' On Linux the browser relies on the system location service, which is often off (on GNOME: Settings, Privacy & Security, Location Services).'
					: ''
			} ${instead}`;
	}
}

/**
 * Great-circle distance in metres between two points (haversine). Accurate
 * to well under a metre at city scale, which is all it is asked for here.
 * @param {{ latitude: number, longitude: number }} a
 * @param {{ latitude: number, longitude: number }} b
 */
export function metresBetween(a, b) {
	const R = 6_371_000;
	const rad = Math.PI / 180;
	const dLat = (b.latitude - a.latitude) * rad;
	const dLng = (b.longitude - a.longitude) * rad;
	const h =
		Math.sin(dLat / 2) ** 2 +
		Math.cos(a.latitude * rad) * Math.cos(b.latitude * rad) * Math.sin(dLng / 2) ** 2;
	return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}
