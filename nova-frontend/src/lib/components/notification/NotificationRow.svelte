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

<div
	class="flex items-center justify-between gap-3 border-b border-slate-100 py-2 last:border-0 dark:border-slate-800"
>
	<div>
		<p class="text-sm font-medium text-slate-900 dark:text-slate-100">
			{notification.template.replaceAll('_', ' ')}
		</p>
		<p class="text-xs text-slate-500 dark:text-slate-400">
			{notification.channel} ·
			{notification.sent_at
				? formatDateTime(notification.sent_at, locale)
				: notification.scheduled_for
					? `scheduled for ${formatDateTime(notification.scheduled_for, locale)}`
					: '—'}
		</p>
		{#if notification.error}
			<p class="text-xs text-red-600">{notification.error}</p>
		{/if}
	</div>
	<Badge tone={statusTone[notification.status] ?? 'neutral'} size="sm">{notification.status}</Badge>
</div>
