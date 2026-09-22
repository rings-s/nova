<script>
	import Badge from '../ui/Badge.svelte';
	import { formatDateTime } from '../../utils/datetime.js';

	/**
	 * @type {{ notification: import('../../api/notification.js').Notification, locale?: 'en'|'ar' }}
	 */
	let { notification, locale = 'en' } = $props();

	/** @type {Record<string, 'neutral'|'success'|'warning'|'error'|'info'|'accent'>} */
	const statusTone = {
		sent: 'info',
		delivered: 'success',
		failed: 'error',
		suppressed: 'neutral',
		scheduled: 'warning'
	};
</script>

<div class="flex items-center justify-between gap-3 border-b border-line-subtle py-3 last:border-0">
	<div class="min-w-0">
		<p class="text-sm font-medium text-fg first-letter:uppercase">
			{notification.template.replaceAll('_', ' ')}
		</p>
		<p class="text-xs text-fg-muted">
			{notification.channel} ·
			{notification.sent_at
				? formatDateTime(notification.sent_at, locale)
				: notification.scheduled_for
					? `scheduled for ${formatDateTime(notification.scheduled_for, locale)}`
					: '—'}
		</p>
		{#if notification.error}
			<p class="mt-0.5 text-xs text-red-600 dark:text-red-400">{notification.error}</p>
		{/if}
	</div>
	<Badge tone={statusTone[notification.status] ?? 'neutral'} size="sm" dot
		>{notification.status}</Badge
	>
</div>
