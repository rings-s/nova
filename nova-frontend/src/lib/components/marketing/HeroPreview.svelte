<script>
	import { t, m } from '$lib/i18n/index.svelte.js';
	/**
	 * The landing page's product preview: a day sheet that runs itself.
	 *
	 * Motion, in three layers, all of it decorative (`aria-hidden`) and all of
	 * it off under `prefers-reduced-motion`, where the card is simply shown:
	 *  1. Entrance. The card swings in from a 3D tilt, its rows cascade, the
	 *     counters count up, and the WhatsApp toast springs in last.
	 *  2. A live loop. Every few seconds the day moves on: a client checks in,
	 *     a treatment starts, a deposit lands, a booking arrives. The badge that
	 *     changed cross-fades, its row glows once, and the toast reports it. The
	 *     loop pauses while the hero is off screen or the tab is hidden.
	 *  3. Depth. With a mouse, the card leans toward the pointer on a spring.
	 *
	 * The server renders the finished state (24 booked, the first toast), so
	 * nothing depends on JavaScript to be readable and hydration matches.
	 */
	import { onMount } from 'svelte';
	import { Spring, Tween } from 'svelte/motion';
	import { cubicOut } from 'svelte/easing';
	import { fade, fly, scale } from 'svelte/transition';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';

	/** @typedef {'success'|'info'|'accent'|'warning'|'neutral'} Tone */
	/** @typedef {{ time: string, name: string, service: string, status: string, tone: Tone }} Row */

	/** @type {Row[]} */
	const START = [
		{
			time: '10:00',
			name: m('Noura A.'),
			service: m('Signature facial'),
			status: m('Checked in'),
			tone: 'info'
		},
		{
			time: '10:30',
			name: m('Sara M.'),
			service: m('Balayage'),
			status: m('In service'),
			tone: 'accent'
		},
		{
			time: '11:15',
			name: m('Reem K.'),
			service: m('Hot stone massage'),
			status: m('Confirmed'),
			tone: 'success'
		},
		{
			time: '12:00',
			name: m('Huda S.'),
			service: m('Laser consultation'),
			status: m('Deposit due'),
			tone: 'warning'
		}
	];

	/** @typedef {{ icon: import('$lib/components/ui/Icon.svelte').IconName, title: string, detail: string, params?: Record<string, string> }} Toast */

	/** @type {Toast} */
	const FIRST_TOAST = {
		icon: 'chat-bubble',
		title: m('Confirmation sent'),
		detail: m('WhatsApp · just now')
	};

	/**
	 * What happens next, in order, then the day starts over. Each beat changes
	 * one row (by index) and says so in the toast.
	 * @type {{ row: number, status: string, tone: Tone, booked?: number, waiting?: number, toast: Toast }[]}
	 */
	const BEATS = [
		{
			row: 2,
			status: m('Checked in'),
			tone: 'info',
			waiting: 4,
			toast: {
				icon: 'user-check',
				title: m('{name} checked in'),
				detail: m('QR ticket scanned · front desk'),
				params: { name: m('Reem K.') }
			}
		},
		{
			row: 0,
			status: m('In service'),
			tone: 'accent',
			waiting: 3,
			toast: {
				icon: 'sparkles',
				title: m('{name} is in the chair'),
				detail: m('Signature facial · 60 min'),
				params: { name: m('Noura A.') }
			}
		},
		{
			row: 3,
			status: m('Confirmed'),
			tone: 'success',
			toast: {
				icon: 'credit-card',
				title: m('Deposit received'),
				detail: m('{name} · paid by mada'),
				params: { name: m('Huda S.') }
			}
		},
		{
			row: 1,
			status: m('Completed'),
			tone: 'neutral',
			booked: 25,
			toast: {
				icon: 'calendar',
				title: m('New booking'),
				detail: m('Marketplace · 4:30 pm tomorrow')
			}
		}
	];
	const BEAT_MS = 3400;

	/** @type {Row[]} */
	let rows = $state(START.map((row) => ({ ...row })));
	/** @type {Toast & { id: number }} */
	let toast = $state({ ...FIRST_TOAST, id: 0 });
	/** The row that just changed, glowing once. @type {number | null} */
	let glowing = $state(null);
	let waiting = $state(3);

	const booked = new Tween(24, { duration: 1200, easing: cubicOut });
	const lean = new Spring({ x: 0, y: 0 }, { stiffness: 0.06, damping: 0.35 });

	/** @type {HTMLDivElement | undefined} */
	let root = $state();

	onMount(() => {
		if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

		// Counted up while the card is still swinging in (it is invisible until then).
		booked.set(0, { duration: 0 });
		const countUp = setTimeout(() => booked.set(24), 450);

		let beat = 0;
		let onScreen = true;
		/** @type {ReturnType<typeof setInterval> | undefined} */
		let timer;
		/** @type {ReturnType<typeof setTimeout> | undefined} */
		let unglow;

		function step() {
			if (beat === BEATS.length) {
				// The day starts over, quietly.
				rows = START.map((row) => ({ ...row }));
				waiting = 3;
				booked.set(24);
				toast = { ...FIRST_TOAST, id: toast.id + 1 };
				beat = 0;
				return;
			}
			const next = BEATS[beat++];
			rows[next.row] = { ...rows[next.row], status: next.status, tone: next.tone };
			if (next.waiting !== undefined) waiting = next.waiting;
			if (next.booked !== undefined) booked.set(next.booked);
			toast = { ...next.toast, id: toast.id + 1 };
			glowing = next.row;
			clearTimeout(unglow);
			unglow = setTimeout(() => (glowing = null), 1400);
		}

		const running = () => onScreen && document.visibilityState === 'visible';
		function sync() {
			if (running() && timer === undefined) timer = setInterval(step, BEAT_MS);
			if (!running() && timer !== undefined) {
				clearInterval(timer);
				timer = undefined;
			}
		}
		// The first beat waits for the entrance to finish.
		const begin = setTimeout(sync, 2400);
		const observer = new IntersectionObserver(([entry]) => {
			onScreen = entry.isIntersecting;
			sync();
		});
		if (root) observer.observe(root);
		document.addEventListener('visibilitychange', sync);

		// Leaning toward the pointer: mouse and trackpad only, never touch.
		const fine = window.matchMedia('(pointer: fine)').matches;
		/** @param {PointerEvent} event */
		function onPointer(event) {
			lean.target = {
				x: (event.clientX / window.innerWidth - 0.5) * 2,
				y: (event.clientY / window.innerHeight - 0.5) * 2
			};
		}
		if (fine) window.addEventListener('pointermove', onPointer, { passive: true });

		return () => {
			clearTimeout(countUp);
			clearTimeout(begin);
			clearTimeout(unglow);
			clearInterval(timer);
			observer.disconnect();
			document.removeEventListener('visibilitychange', sync);
			window.removeEventListener('pointermove', onPointer);
		};
	});

	// Resting tilt, plus the lean: a few degrees, never enough to blur text.
	let transform = $derived(
		`perspective(1400px) rotateX(${(4 - lean.current.y * 5).toFixed(2)}deg) rotateY(${(
			-6 +
			lean.current.x * 7
		).toFixed(2)}deg)`
	);
</script>

<div bind:this={root} class="preview relative" aria-hidden="true">
	<div class="card-tilt" style:transform>
		<div
			class="card-in rounded-panel border border-line bg-surface/90 p-2 shadow-overlay backdrop-blur-xl"
		>
			<div class="rounded-[calc(var(--radius-panel)-0.5rem)] border border-line-subtle bg-surface">
				<div class="flex items-center justify-between border-b border-line-subtle px-5 py-4">
					<div>
						<p class="flex items-center gap-1.5 text-xs text-fg-muted">
							<span class="live-dot relative flex size-1.5">
								<span class="absolute inset-0 rounded-full bg-emerald-500"></span>
							</span>
							{t('Today · Olaya branch')}
						</p>
						<p class="font-semibold text-fg">{t('Day sheet')}</p>
					</div>
					<div class="flex gap-4 text-end">
						<div>
							<p class="text-[11px] text-fg-muted">{t('Booked')}</p>
							<p class="text-lg font-semibold text-fg tabular-nums">
								{Math.round(booked.current)}
							</p>
						</div>
						<div>
							<p class="text-[11px] text-fg-muted">{t('Waiting')}</p>
							<p class="relative h-7 overflow-hidden text-lg font-semibold text-fg tabular-nums">
								{#key waiting}
									<span
										class="block"
										in:fly={{ y: 14, duration: 380, easing: cubicOut }}
										out:fly={{ y: -14, duration: 260 }}
									>
										{waiting}
									</span>
								{/key}
							</p>
						</div>
					</div>
				</div>
				<ul class="divide-y divide-line-subtle">
					{#each rows as row, i (row.time)}
						<li
							class="row flex items-center gap-4 px-5 py-3"
							class:glow={glowing === i}
							style:--i={i}
						>
							<span class="w-12 text-sm font-semibold text-accent tabular-nums">{row.time}</span>
							<div class="min-w-0 flex-1">
								<p class="truncate text-sm font-medium text-fg">{t(row.name)}</p>
								<p class="truncate text-xs text-fg-muted">{t(row.service)}</p>
							</div>
							<span class="grid place-items-end">
								{#key row.status}
									<span
										class="[grid-area:1/1]"
										in:scale={{ start: 0.85, duration: 420, easing: cubicOut }}
										out:fade={{ duration: 200 }}
									>
										<Badge tone={row.tone} size="sm" dot>{t(row.status)}</Badge>
									</span>
								{/key}
							</span>
						</li>
					{/each}
				</ul>
			</div>
		</div>
	</div>

	<div class="toast-slot absolute -start-6 -bottom-12 hidden sm:block">
		{#key toast.id}
			<div
				class="toast flex items-center gap-3 rounded-card border border-line bg-surface px-4 py-3 shadow-raised"
				in:fly={{ y: 12, duration: 520, easing: cubicOut }}
				out:fade={{ duration: 180 }}
			>
				<span
					class="flex size-9 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400"
				>
					<Icon name={toast.icon} class="size-4" />
				</span>
				<div>
					<p class="text-xs font-semibold text-fg">{t(toast.title, toast.params)}</p>
					<p class="text-[11px] text-fg-muted">{t(toast.detail, toast.params)}</p>
				</div>
			</div>
		{/key}
	</div>
</div>

<style>
	/* The card swings in from a tilt, then settles into its resting lean. */
	.card-tilt {
		transform-style: preserve-3d;
		will-change: transform;
	}
	.card-in {
		animation: card-in 1s var(--ease-out-premium) 0.25s both;
	}
	@keyframes card-in {
		from {
			opacity: 0;
			transform: translateY(40px) rotateX(18deg) rotateY(-14deg) scale(0.94);
		}
	}

	/* Rows cascade in after the card. */
	.row {
		animation: row-in 0.6s var(--ease-out-premium) both;
		animation-delay: calc(0.65s + var(--i) * 90ms);
		transition: background-color 1.2s var(--ease-out-premium);
	}
	@keyframes row-in {
		from {
			opacity: 0;
			transform: translateX(calc(16px * var(--dir-sign, 1)));
		}
	}
	/* The row that just changed glows once, then fades back. */
	.row.glow {
		background-color: color-mix(in oklch, var(--color-brand-500) 7%, transparent);
		transition-duration: 0.2s;
	}

	/* The first toast springs in last; later ones are Svelte transitions. */
	.toast-slot {
		animation: toast-pop 0.7s cubic-bezier(0.34, 1.56, 0.64, 1) 1.5s both;
	}
	@keyframes toast-pop {
		from {
			opacity: 0;
			transform: translateY(10px) scale(0.85);
		}
	}

	/* "Live": a soft ring breathing out of the green dot. */
	.live-dot::after {
		content: '';
		position: absolute;
		inset: 0;
		border-radius: 9999px;
		background: var(--color-emerald-500, #10b981);
		animation: ping 2s cubic-bezier(0, 0, 0.2, 1) infinite;
	}
	@keyframes ping {
		75%,
		100% {
			transform: scale(3);
			opacity: 0;
		}
	}
</style>
