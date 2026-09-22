/**
 * Class recipes shared by more than one primitive, so a text field, a select
 * and a textarea can never drift apart in height, border, focus or error
 * treatment. Colors are the semantic tokens from `routes/layout.css`; none
 * of these needs a `dark:` variant.
 */

/** The control itself: input, select, textarea. */
export const fieldBase = [
	'w-full rounded-control border bg-surface px-3 text-sm text-fg shadow-card',
	'placeholder:text-fg-subtle',
	'transition-[border-color,box-shadow] duration-fast ease-out-premium',
	'hover:border-fg-subtle',
	'focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15 focus:outline-none',
	'disabled:cursor-not-allowed disabled:bg-surface-muted disabled:opacity-60'
].join(' ');

/** Border color for a field, by validity. */
/** @param {boolean} invalid */
export function fieldBorder(invalid) {
	return invalid
		? 'border-red-400 focus:border-red-500 focus:ring-red-500/15 dark:border-red-500/70'
		: 'border-line-strong';
}

export const fieldLabel = 'text-sm font-medium text-fg-secondary';
export const fieldHint = 'text-xs text-fg-muted';
export const fieldError = 'text-xs font-medium text-red-600 dark:text-red-400';

/** A small square icon button: modal close, alert dismiss, theme toggle. */
export const iconButton =
	'inline-flex shrink-0 items-center justify-center rounded-control text-fg-muted transition-colors duration-fast hover:bg-surface-muted hover:text-fg focus-ring';
