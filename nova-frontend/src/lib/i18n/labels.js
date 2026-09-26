/**
 * Names for the backend's enum values (statuses, sources, roles), in the
 * active language. One place, so a booking status reads the same on every
 * page that shows it.
 */
import { m, t } from './index.svelte.js';

/** @param {Record<string, string>} table @param {string|null|undefined} value */
function label(table, value) {
	if (!value) return '';
	return t(table[value] ?? value.replaceAll('_', ' '));
}

const BOOKING_STATUS = {
	draft: m('Draft'),
	pending_payment: m('Pending payment'),
	confirmed: m('Confirmed'),
	checked_in: m('Checked in'),
	in_service: m('In service'),
	completed: m('Completed'),
	cancelled: m('Cancelled'),
	no_show: m('No-show')
};

const PAYMENT_STATUS = {
	pending: m('Pending'),
	authorized: m('Authorized'),
	processing: m('Processing'),
	captured: m('Paid'),
	failed: m('Failed'),
	refunded: m('Refunded'),
	partially_refunded: m('Partially refunded'),
	cancelled: m('Cancelled')
};

const QUEUE_STATUS = {
	waiting: m('Waiting'),
	called: m('Called'),
	checked_in: m('Checked in'),
	in_service: m('In service'),
	completed: m('Completed'),
	missed: m('Missed'),
	cancelled: m('Cancelled'),
	left: m('Left')
};

const BOOKING_SOURCE = {
	marketplace: m('Marketplace'),
	direct_link: m('Direct link'),
	whatsapp: m('WhatsApp'),
	walk_in: m('Walk-in'),
	reception: m('Reception'),
	ai_agent: m('AI assistant')
};

const NOTIFICATION_STATUS = {
	scheduled: m('Scheduled'),
	sent: m('Sent'),
	delivered: m('Delivered'),
	read: m('Read'),
	failed: m('Failed'),
	suppressed: m('Suppressed')
};

const NOTIFICATION_CHANNEL = {
	whatsapp: m('WhatsApp'),
	sms: m('SMS'),
	email: m('Email')
};

const ROLE = {
	owner: m('Owner'),
	manager: m('Manager'),
	receptionist: m('Receptionist'),
	provider: m('Provider')
};

/** @param {string|null|undefined} status */
export const bookingStatusLabel = (status) => label(BOOKING_STATUS, status);
/** @param {string|null|undefined} status */
export const paymentStatusLabel = (status) => label(PAYMENT_STATUS, status);
/** @param {string|null|undefined} status */
export const queueStatusLabel = (status) => label(QUEUE_STATUS, status);
/** @param {string|null|undefined} source */
export const bookingSourceLabel = (source) => label(BOOKING_SOURCE, source);
/** @param {string|null|undefined} status */
export const notificationStatusLabel = (status) => label(NOTIFICATION_STATUS, status);
/** @param {string|null|undefined} channel */
export const notificationChannelLabel = (channel) => label(NOTIFICATION_CHANNEL, channel);
/** @param {string|null|undefined} role */
export const roleLabel = (role) => label(ROLE, role);

/**
 * A duration in minutes, e.g. "45 min".
 * @param {number|null|undefined} minutes
 */
export function minutesLabel(minutes) {
	return t('{minutes} min', { minutes: minutes ?? 0 });
}
