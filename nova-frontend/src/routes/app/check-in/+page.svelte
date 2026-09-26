<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * Reception checks a customer in by their QR ticket (docs/09 #8).
	 *
	 * Two ways in, both ending at `POST /tickets/check-in`:
	 * - the device camera, read frame by frame with jsQR (it works in every
	 *   browser, where the native BarcodeDetector does not);
	 * - the text field, which a USB or Bluetooth barcode scanner types into
	 *   like a keyboard, ending with Enter. Staff can paste a code there too.
	 *
	 * The server checks the signature, the tenant, the status and the expiry,
	 * and answers every failure the same way on purpose (docs/07 section 7), so
	 * this page can only say "not valid here". Scanning the same code twice is
	 * harmless: redemption is idempotent.
	 */
	import { onDestroy } from 'svelte';
	import jsQR from 'jsqr';
	import { tenantStore } from '$lib/stores/tenant.svelte.js';
	import { checkInWithTicket } from '$lib/api/queue.js';
	import { getBooking } from '$lib/api/booking.js';
	import { ApiError } from '$lib/api/client.js';
	import { errorMessage } from '$lib/utils/errors.js';
	import { formatDateTime } from '$lib/utils/datetime.js';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { fieldBase, fieldBorder } from '$lib/components/ui/styles.js';
	import BookingStatusBadge from '$lib/components/booking/BookingStatusBadge.svelte';

	let tenantId = $derived(tenantStore.activeTenantId);

	let code = $state('');
	let checking = $state(false);
	/** @type {{ ok: true, ticketCode: string, booking: import('$lib/api/booking.js').Booking|null, redeemedAt: string|null } | { ok: false, message: string } | null} */
	let result = $state(null);

	let scanning = $state(false);
	let cameraError = $state(/** @type {string|null} */ (null));
	/** @type {HTMLVideoElement|undefined} */
	let video = $state();
	/** @type {MediaStream|null} */
	let stream = null;
	let frame = 0;
	/** The last code sent, so a camera held on one QR does not resend it every frame. */
	let lastScanned = '';
	const canvas = typeof document !== 'undefined' ? document.createElement('canvas') : null;

	/** Refusals the server means, in reception's words. @param {unknown} err */
	function explain(err) {
		if (err instanceof ApiError) {
			if (err.code === 'ticket_invalid') return t('This ticket is not valid for this business.');
			if (err.code === 'ticket_expired') return t('This ticket has expired.');
			if (err.code === 'invalid_booking_transition')
				return t('This booking is not confirmed yet. Confirm it in Bookings, then scan again.');
		}
		return errorMessage(err);
	}

	/** @param {string} payload */
	async function checkIn(payload) {
		payload = payload.trim();
		if (!payload || !tenantId || checking) return;
		checking = true;
		try {
			const outcome = await checkInWithTicket(tenantId, payload);
			const booking = outcome.ticket.booking_id
				? await getBooking(tenantId, outcome.ticket.booking_id).catch(() => null)
				: null;
			result = {
				ok: true,
				ticketCode: outcome.ticket.ticket_code,
				booking,
				redeemedAt: outcome.ticket.redeemed_at
			};
			code = '';
		} catch (err) {
			result = { ok: false, message: explain(err) };
		} finally {
			checking = false;
		}
	}

	/** @param {SubmitEvent} event */
	function submit(event) {
		event.preventDefault();
		checkIn(code);
	}

	async function startCamera() {
		cameraError = null;
		try {
			stream = await navigator.mediaDevices.getUserMedia({
				video: { facingMode: 'environment' },
				audio: false
			});
		} catch {
			cameraError = t(
				'The camera is not available. Allow camera access, or type or scan the code below.'
			);
			return;
		}
		scanning = true;
		lastScanned = '';
		// The <video> renders once `scanning` is true.
		requestAnimationFrame(() => {
			if (!video || !stream) return;
			video.srcObject = stream;
			video.play().catch(() => {});
			frame = requestAnimationFrame(readFrame);
		});
	}

	function stopCamera() {
		cancelAnimationFrame(frame);
		stream?.getTracks().forEach((track) => track.stop());
		stream = null;
		scanning = false;
	}

	function readFrame() {
		if (!scanning || !video || !canvas) return;
		if (video.readyState === video.HAVE_ENOUGH_DATA && !checking) {
			canvas.width = video.videoWidth;
			canvas.height = video.videoHeight;
			const context = canvas.getContext('2d', { willReadFrequently: true });
			if (context) {
				context.drawImage(video, 0, 0, canvas.width, canvas.height);
				const image = context.getImageData(0, 0, canvas.width, canvas.height);
				const found = jsQR(image.data, image.width, image.height, {
					inversionAttempts: 'dontInvert'
				});
				if (found?.data && found.data !== lastScanned) {
					lastScanned = found.data;
					checkIn(found.data);
				}
			}
		}
		frame = requestAnimationFrame(readFrame);
	}

	onDestroy(stopCamera);
</script>

<svelte:head><title>{t('Check-in')} — NOVA</title></svelte:head>

<PageHeader
	eyebrow={t('Operate')}
	title={t('Check-in')}
	subtitle={t("Scan a customer's QR ticket to check them in for their appointment.")}
/>

<div class="grid items-start gap-6 lg:grid-cols-2">
	<Card padding="lg">
		<div class="flex items-center justify-between gap-3">
			<h2 class="font-semibold text-fg">{t('Scan with the camera')}</h2>
			{#if scanning}
				<Button size="sm" variant="outline" onclick={stopCamera}>{t('Stop camera')}</Button>
			{/if}
		</div>

		{#if scanning}
			<div class="relative mt-4 overflow-hidden rounded-control bg-black">
				<video bind:this={video} class="aspect-square w-full object-cover" playsinline muted
				></video>
				<div
					class="pointer-events-none absolute inset-[18%] rounded-card border-2 border-white/80"
					aria-hidden="true"
				></div>
			</div>
			<p class="mt-2 text-xs text-fg-muted">{t('Hold the QR code inside the frame.')}</p>
		{:else}
			<button
				type="button"
				onclick={startCamera}
				class="mt-4 flex aspect-square w-full flex-col items-center justify-center gap-3 rounded-control border border-dashed border-line-strong bg-surface-sunken text-fg-secondary focus-ring transition-colors duration-fast hover:text-fg"
			>
				<Icon name="shield-check" class="size-8" />
				<span class="text-sm font-medium">{t('Start camera')}</span>
			</button>
		{/if}
		{#if cameraError}<Alert tone="warning" class="mt-3">{cameraError}</Alert>{/if}

		<form class="mt-6" onsubmit={submit}>
			<label class="text-sm font-medium text-fg" for="ticket-code">
				{t('Or scan / paste the ticket code')}
			</label>
			<div class="mt-1.5 flex gap-2">
				<!-- svelte-ignore a11y_autofocus -->
				<input
					id="ticket-code"
					bind:value={code}
					autocomplete="off"
					autofocus
					dir="ltr"
					class={[fieldBase, fieldBorder, 'flex-1 font-mono text-sm'].join(' ')}
					placeholder={t('Code from the QR')}
				/>
				<Button type="submit" loading={checking} disabled={!code.trim()}>{t('Check in')}</Button>
			</div>
			<p class="mt-1.5 text-xs text-fg-muted">
				{t('A handheld barcode scanner can type the code here directly.')}
			</p>
		</form>
	</Card>

	<div aria-live="polite">
		{#if result?.ok}
			<Card padding="lg" class="border-emerald-500/40">
				<div class="flex items-center gap-3">
					<span
						class="flex size-10 items-center justify-center rounded-full bg-emerald-500 text-white"
					>
						<Icon name="check" class="size-5" />
					</span>
					<div>
						<p class="font-semibold text-fg">{t('Checked in')}</p>
						<p class="font-mono text-sm text-fg-muted" dir="ltr">{result.ticketCode}</p>
					</div>
				</div>
				{#if result.booking}
					<dl class="mt-5 space-y-2 text-sm">
						<div class="flex justify-between gap-4">
							<dt class="text-fg-muted">{t('Appointment')}</dt>
							<dd class="text-fg">{formatDateTime(result.booking.starts_at)}</dd>
						</div>
						<div class="flex justify-between gap-4">
							<dt class="text-fg-muted">{t('Status')}</dt>
							<dd><BookingStatusBadge status={result.booking.status} /></dd>
						</div>
					</dl>
				{/if}
			</Card>
		{:else if result && !result.ok}
			<Alert tone="error">{result.message}</Alert>
		{:else}
			<Card padding="lg">
				<p class="text-sm text-fg-muted">
					{t('The result of each scan appears here. Scanning the same ticket twice is safe.')}
				</p>
			</Card>
		{/if}
	</div>
</div>
