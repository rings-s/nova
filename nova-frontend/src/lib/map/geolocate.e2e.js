import { expect, test } from '@playwright/test';
import {
	LocateError,
	PIN_WORTHY_M,
	PRECISE_ENOUGH_M,
	describeAccuracy,
	explainFix,
	explainLocateError,
	locate
} from './geolocate.js';

// `locate` against a scripted provider. Pure JavaScript, so these need no page:
// they run in Playwright only because it is the project's one test runner.

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

/** A position, as the browser hands one to a success callback. */
const position = (/** @type {number} */ accuracy, latitude = 24.7136, longitude = 46.6753) => ({
	coords: { latitude, longitude, accuracy }
});
/** An error, as the browser hands one to an error callback. */
const failure = (/** @type {number} */ code, message = '') => ({ code, message });

/**
 * A provider that does nothing until the test says so.
 * @param {{ answerWatchImmediately?: ReturnType<typeof position> }} [options]
 */
function scriptedProvider({ answerWatchImmediately } = {}) {
	/** @type {{ ok: Function, err: Function, options: PositionOptions }[]} */
	const current = [];
	/** @type {{ ok: Function, err: Function, options: PositionOptions }[]} */
	const watches = [];
	/** @type {number[]} */
	const cleared = [];
	const geolocation = /** @type {Geolocation} */ (
		/** @type {unknown} */ ({
			getCurrentPosition: (
				/** @type {Function} */ ok,
				/** @type {Function} */ err,
				/** @type {PositionOptions} */ options
			) => {
				current.push({ ok, err, options });
			},
			watchPosition: (
				/** @type {Function} */ ok,
				/** @type {Function} */ err,
				/** @type {PositionOptions} */ options
			) => {
				watches.push({ ok, err, options });
				if (answerWatchImmediately) ok(answerWatchImmediately);
				return watches.length;
			},
			clearWatch: (/** @type {number} */ id) => {
				cleared.push(id);
			}
		})
	);
	return { geolocation, current, watches, cleared };
}

/** Collects each fix `onfix` is told about. */
function collector() {
	/** @type {number[]} */
	const accuracies = [];
	return {
		accuracies,
		onfix: (/** @type {{ accuracy: number }} */ fix) => accuracies.push(fix.accuracy)
	};
}

test.describe('locate: getting a fix', () => {
	test('a precise first fix ends the search at once, with no watch started', async () => {
		const p = scriptedProvider();
		const { accuracies, onfix } = collector();
		const done = locate({ geolocation: p.geolocation, secure: true, onfix });

		p.current[0].ok(position(12));

		expect(await done).toMatchObject({ accuracy: 12, latitude: 24.7136, longitude: 46.6753 });
		expect(accuracies).toEqual([12]);
		expect(p.watches).toHaveLength(0);
	});

	test('the quick request is tolerant: a cached fix is fine and GPS is not demanded', async () => {
		const p = scriptedProvider();
		locate({ geolocation: p.geolocation, secure: true, onfix: () => {} });

		expect(p.current[0].options).toMatchObject({ enableHighAccuracy: false, maximumAge: 60_000 });
	});

	test('a rough first fix is refined by a watch for a precise one', async () => {
		const p = scriptedProvider();
		const { accuracies, onfix } = collector();
		const done = locate({ geolocation: p.geolocation, secure: true, onfix, refineMs: 2000 });

		p.current[0].ok(position(800));
		await tick();
		expect(p.watches).toHaveLength(1);
		expect(p.watches[0].options).toMatchObject({ enableHighAccuracy: true, maximumAge: 0 });
		p.watches[0].ok(position(9));

		expect(await done).toMatchObject({ accuracy: 9 });
		expect(accuracies).toEqual([800, 9]);
		expect(p.cleared).toEqual([1]); // stopped watching the moment it was good enough
	});

	test('a worse fix arriving later never replaces a better one', async () => {
		const p = scriptedProvider();
		const { accuracies, onfix } = collector();
		const done = locate({ geolocation: p.geolocation, secure: true, onfix, refineMs: 80 });

		p.current[0].ok(position(200));
		await tick();
		p.watches[0].ok(position(500)); // worse: dropped
		p.watches[0].ok(position(90)); // better: kept
		p.watches[0].ok(position(300)); // worse than 90: dropped

		expect(await done).toMatchObject({ accuracy: 90 });
		expect(accuracies).toEqual([200, 90]);
	});

	test('the search ends with the best fix when the refining window closes', async () => {
		const p = scriptedProvider();
		const done = locate({
			geolocation: p.geolocation,
			secure: true,
			onfix: () => {},
			refineMs: 40
		});

		p.current[0].ok(position(400));

		expect(await done).toMatchObject({ accuracy: 400 });
		expect(p.cleared).toEqual([1]);
	});

	test('a device whose quick request fails can still be found by the watch (GPS only)', async () => {
		const p = scriptedProvider();
		const done = locate({
			geolocation: p.geolocation,
			secure: true,
			onfix: () => {},
			refineMs: 2000
		});

		p.current[0].err(failure(2, 'no network location'));
		await tick();
		p.watches[0].ok(position(15));

		expect(await done).toMatchObject({ accuracy: 15 });
	});

	test('a provider that answers before watchPosition has returned is still stopped', async () => {
		const p = scriptedProvider({ answerWatchImmediately: position(10) });
		const done = locate({
			geolocation: p.geolocation,
			secure: true,
			onfix: () => {},
			refineMs: 2000
		});

		p.current[0].ok(position(700));

		expect(await done).toMatchObject({ accuracy: 10 });
		expect(p.cleared).toEqual([1]);
	});

	test('an accuracy of zero is never zero, and a missing one is treated as rough', async () => {
		const zero = scriptedProvider();
		const first = locate({ geolocation: zero.geolocation, secure: true, onfix: () => {} });
		zero.current[0].ok(position(0));
		expect((await first).accuracy).toBe(1);

		const missing = scriptedProvider();
		const second = locate({
			geolocation: missing.geolocation,
			secure: true,
			onfix: () => {},
			refineMs: 20
		});
		missing.current[0].ok({ coords: { latitude: 1, longitude: 1 } });
		expect((await second).accuracy).toBeGreaterThan(PIN_WORTHY_M);
	});
});

test.describe('locate: when there is no fix', () => {
	/** @param {Promise<unknown>} promise */
	const failedWith = async (promise) => {
		try {
			await promise;
		} catch (error) {
			return /** @type {LocateError} */ (error);
		}
		throw new Error('expected locate to fail');
	};

	test('refusing permission ends it at once, and the watch is never started', async () => {
		const p = scriptedProvider();
		const done = failedWith(locate({ geolocation: p.geolocation, secure: true, onfix: () => {} }));

		p.current[0].err(failure(1, 'User denied Geolocation'));

		const error = await done;
		expect(error).toBeInstanceOf(LocateError);
		expect(error.kind).toBe('denied');
		expect(p.watches).toHaveLength(0);
	});

	test("nothing found: the first failure is the one reported, with the browser's own words", async () => {
		const p = scriptedProvider();
		const done = failedWith(
			locate({ geolocation: p.geolocation, secure: true, onfix: () => {}, refineMs: 2000 })
		);

		p.current[0].err(failure(2, 'Unknown error acquiring position'));
		await tick();
		// The watch fails too. With nothing found, waiting out its window would
		// only delay the answer, so the search ends here.
		p.watches[0].err(failure(3, 'Timeout expired'));

		const error = await done;
		expect(error.kind).toBe('unavailable');
		expect(error.detail).toBe('Unknown error acquiring position');
		expect(p.cleared).toEqual([1]);
	});

	test('a timeout is reported as one', async () => {
		const p = scriptedProvider();
		const done = failedWith(
			locate({ geolocation: p.geolocation, secure: true, onfix: () => {}, refineMs: 2000 })
		);

		p.current[0].err(failure(3, 'Timeout expired'));
		await tick();
		p.watches[0].err(failure(3, 'Timeout expired'));

		expect((await done).kind).toBe('timeout');
	});

	test('an insecure page never asks the browser', async () => {
		const p = scriptedProvider();

		const error = await failedWith(
			locate({ geolocation: p.geolocation, secure: false, onfix: () => {} })
		);

		expect(error.kind).toBe('insecure');
		expect(p.current).toHaveLength(0);
	});

	test('a browser with no geolocation says so', async () => {
		// `undefined` falls through to the runtime's own `navigator`, which under
		// Node has no `geolocation`.
		const error = await failedWith(
			locate({ geolocation: undefined, secure: true, onfix: () => {} })
		);

		expect(error.kind).toBe('unsupported');
	});

	test('cancelling during the quick request rejects as cancelled', async () => {
		const p = scriptedProvider();
		const controller = new AbortController();
		const done = failedWith(
			locate({
				geolocation: p.geolocation,
				secure: true,
				onfix: () => {},
				signal: controller.signal
			})
		);

		controller.abort();

		expect((await done).kind).toBe('cancelled');
		expect(p.watches).toHaveLength(0);
	});

	test('cancelling while refining keeps the best fix so far and stops the watch', async () => {
		const p = scriptedProvider();
		const controller = new AbortController();
		const done = locate({
			geolocation: p.geolocation,
			secure: true,
			onfix: () => {},
			signal: controller.signal,
			refineMs: 5000
		});
		p.current[0].ok(position(600));
		await tick();

		controller.abort();

		expect(await done).toMatchObject({ accuracy: 600 });
		expect(p.cleared).toEqual([1]);
	});

	test('cancelling while refining with nothing found rejects as cancelled', async () => {
		const p = scriptedProvider();
		const controller = new AbortController();
		const done = failedWith(
			locate({
				geolocation: p.geolocation,
				secure: true,
				onfix: () => {},
				signal: controller.signal,
				refineMs: 5000
			})
		);
		p.current[0].err(failure(3));
		await tick();

		controller.abort();

		expect((await done).kind).toBe('cancelled');
		expect(p.cleared).toEqual([1]);
	});
});

test.describe('telling the owner', () => {
	test('accuracy reads as metres, then kilometres', () => {
		expect(describeAccuracy(12.4)).toBe('12 m');
		expect(describeAccuracy(999)).toBe('999 m');
		expect(describeAccuracy(3400)).toBe('3.4 km');
		expect(describeAccuracy(41_000)).toBe('41 km');
	});

	test('a fix places a pin only if it is good enough to trust with one', () => {
		expect(explainFix({ latitude: 0, longitude: 0, accuracy: PRECISE_ENOUGH_M })).toMatchObject({
			pin: true,
			tone: 'success'
		});
		expect(explainFix({ latitude: 0, longitude: 0, accuracy: 400 })).toMatchObject({
			pin: true,
			tone: 'success'
		});
		expect(explainFix({ latitude: 0, longitude: 0, accuracy: PIN_WORTHY_M })).toMatchObject({
			pin: true
		});
		const rough = explainFix({ latitude: 0, longitude: 0, accuracy: PIN_WORTHY_M + 1 });
		expect(rough).toMatchObject({ pin: false, tone: 'warning' });
		expect(rough.text).toContain('too rough for a pin');
	});

	test('every failure says what to do, and the Linux hint appears only where it applies', () => {
		const message = (
			/** @type {import('./geolocate.js').LocateFailure} */ kind,
			/** @type {{ origin?: string, linux?: boolean }} */ context = {}
		) => explainLocateError(new LocateError(kind), context);

		expect(message('denied')).toContain('blocked');
		expect(message('timeout')).toContain('did not answer in time');
		expect(message('unsupported')).toContain('cannot share');
		expect(message('insecure', { origin: 'http://192.168.1.5:5173' })).toContain(
			'http://192.168.1.5:5173'
		);
		expect(message('unavailable')).not.toContain('Location Services');
		expect(message('unavailable', { linux: true })).toContain('Location Services');
		expect(message('denied', { linux: true })).not.toContain('Location Services');
		for (const kind of /** @type {const} */ (['denied', 'timeout', 'unavailable', 'insecure'])) {
			expect(message(kind).toLowerCase()).toContain('click the map');
		}
	});
});
