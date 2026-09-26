<script>
	import { notificationChannelLabel, notificationStatusLabel } from '$lib/i18n/labels.js';
	import { t } from '$lib/i18n/index.svelte.js';
	import Badge from '../ui/Badge.svelte';
	import { formatDateTime } from '../../utils/datetime.js';

	/**
	 * @type {{ notification: import('../../api/notification.js').Notification, locale?: 'en'|'ar' }}
	 */
	let { notification } = $props();

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
			{notificationChannelLabel(notification.channel)} ·
			{notification.sent_at
				? formatDateTime(notification.sent_at)
				: notification.scheduled_for
					? t('scheduled for {time}', { time: formatDateTime(notification.scheduled_for) })
					: '—'}
		</p>
		{#if notification.error}
			<p class="mt-0.5 text-xs text-red-600 dark:text-red-400">{notification.error}</p>
		{/if}
	</div>
	<Badge tone={statusTone[notification.status] ?? 'neutral'} size="sm" dot
		>{notificationStatusLabel(notification.status)}</Badge
	>
</div>
