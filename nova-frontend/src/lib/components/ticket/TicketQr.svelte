<script>
	/**
	 * A ticket's QR code, drawn as one SVG path.
	 *
	 * Always dark modules on white with a quiet zone, whatever the theme: a
	 * scanner reads contrast, and an inverted code fails on many of them.
	 * `payload` is the ticket's `qr_payload` — the check-in credential — so it
	 * is rendered and never put in a URL, a log or local storage by this
	 * component.
	 */
	import { encode } from 'uqr';

	/** @type {{ payload: string, label: string, class?: string }} */
	let { payload, label, class: className = 'size-56' } = $props();

	/** Four modules of white around the code, as the QR spec asks. */
	const QUIET = 4;

	let qr = $derived(encode(payload, { ecc: 'M' }));
	let path = $derived.by(() => {
		let d = '';
		qr.data.forEach((row, y) => {
			row.forEach((dark, x) => {
				if (dark) d += `M${x + QUIET} ${y + QUIET}h1v1h-1z`;
			});
		});
		return d;
	});
	let extent = $derived(qr.size + QUIET * 2);
</script>

<svg
	viewBox={`0 0 ${extent} ${extent}`}
	class={['rounded-control bg-white', className].join(' ')}
	role="img"
	aria-label={label}
	shape-rendering="crispEdges"
>
	<rect width={extent} height={extent} fill="#fff" />
	<path d={path} fill="#000" />
</svg>
