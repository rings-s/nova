<script>
	import Badge from '../ui/Badge.svelte';

	/** @type {{ status: import('../../api/booking.js').BookingStatus }} */
	let { status } = $props();

	/** @type {Record<string, { tone: 'neutral'|'success'|'warning'|'error'|'info'|'accent', label: string }>} */
	const map = {
		draft: { tone: 'neutral', label: 'Draft' },
		pending_payment: { tone: 'warning', label: 'Pending payment' },
		confirmed: { tone: 'success', label: 'Confirmed' },
		checked_in: { tone: 'info', label: 'Checked in' },
		in_service: { tone: 'accent', label: 'In service' },
		completed: { tone: 'success', label: 'Completed' },
		cancelled: { tone: 'neutral', label: 'Cancelled' },
		no_show: { tone: 'error', label: 'No-show' }
	};

	let entry = $derived(map[status] ?? { tone: 'neutral', label: status });
</script>

<Badge tone={entry.tone}>{entry.label}</Badge>
