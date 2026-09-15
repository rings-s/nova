<script>
	import Badge from '../ui/Badge.svelte';

	/** @type {{ status: import('../../api/payment.js').PaymentStatus }} */
	let { status } = $props();

	/** @type {Record<string, { tone: 'neutral'|'success'|'warning'|'error'|'info'|'accent', label: string }>} */
	const map = {
		pending: { tone: 'neutral', label: 'Pending' },
		processing: { tone: 'info', label: 'Processing' },
		captured: { tone: 'success', label: 'Captured' },
		failed: { tone: 'error', label: 'Failed' },
		refunded: { tone: 'warning', label: 'Refunded' },
		partially_refunded: { tone: 'warning', label: 'Partially refunded' },
		cancelled: { tone: 'neutral', label: 'Cancelled' }
	};

	let entry = $derived(map[status] ?? { tone: 'neutral', label: status });
</script>

<Badge tone={entry.tone}>{entry.label}</Badge>
