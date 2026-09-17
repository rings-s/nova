<script module>
	/**
	 * @typedef {'calendar'|'chat-bubble'|'users'|'chart-bar'|'credit-card'|'shield-check'|'globe'|'sparkles'|'check'|'chevron-left'|'chevron-right'|'arrow-right'|'x'|'user-check'|'phone'|'search'|'clock'|'map-pin'|'star'|'filter'|'zap'|'building'|'trending-up'} IconName
	 */

	/**
	 * Path data for each glyph, 24x24, drawn for a stroked (not filled)
	 * presentation. Kept as plain `<path>`/`<g>` fragments so new glyphs are a
	 * one-entry addition here rather than a new component per icon.
	 * @type {Record<IconName, string>}
	 */
	const ICONS = {
		calendar:
			'<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 9.5h17M8 3v3.5M16 3v3.5"/>',
		'chat-bubble':
			'<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8A2.5 2.5 0 0 1 17.5 16H10l-4.5 4v-4H6.5A2.5 2.5 0 0 1 4 13.5z"/>',
		users:
			'<circle cx="9" cy="8" r="3"/><path d="M3.5 19.5c0-3 2.5-5 5.5-5s5.5 2 5.5 5"/><circle cx="17" cy="9" r="2.3"/><path d="M15.5 12.2c2.4.3 4 2 4 4.6"/>',
		'chart-bar': '<path d="M4 20V13M11 20V9M18 20v-7M3 20h18"/>',
		'credit-card': '<rect x="3" y="5.5" width="18" height="13" rx="2"/><path d="M3 10h18"/>',
		'shield-check':
			'<path d="M12 3.5 19 6.5v5.2c0 4.4-3 7.4-7 8.8-4-1.4-7-4.4-7-8.8V6.5z"/><path d="M9 12l2 2 4-4.2"/>',
		globe:
			'<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.3 3.7 5.2 3.7 8.5s-1.3 6.2-3.7 8.5c-2.4-2.3-3.7-5.2-3.7-8.5S9.6 5.8 12 3.5z"/>',
		sparkles:
			'<path d="M11.5 3.5 13 8l4.5 1.5L13 11l-1.5 4.5L10 11l-4.5-1.5L10 8z"/><path d="M18.5 15.5l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/>',
		check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
		'chevron-left': '<path d="M14.5 5.5 8 12l6.5 6.5"/>',
		'chevron-right': '<path d="M9.5 5.5 16 12l-6.5 6.5"/>',
		'arrow-right': '<path d="M4.5 12h15M13.5 5.5 20 12l-6.5 6.5"/>',
		x: '<path d="M6 6l12 12M18 6L6 18"/>',
		'user-check':
			'<circle cx="9" cy="8" r="3.5"/><path d="M3.5 19.5c0-3.3 2.5-5.5 5.5-5.5s5.5 2.2 5.5 5.5"/><path d="M16 13.5l1.8 1.8 3.2-3.4"/>',
		phone:
			'<path d="M6 3.5h3l1.2 4-2 1.5a11 11 0 0 0 5.3 5.3l1.5-2 4 1.2v3a1.5 1.5 0 0 1-1.6 1.5A15.5 15.5 0 0 1 4.5 5.1 1.5 1.5 0 0 1 6 3.5z"/>',
		search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
		clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
		'map-pin':
			'<path d="M12 21s-7-5.5-7-11.5a7 7 0 0 1 14 0c0 6-7 11.5-7 11.5z"/><circle cx="12" cy="9.5" r="2.5"/>',
		star: '<path d="m12 2.5 2.8 6 6.6.6-5 4.5 1.5 6.4-5.9-3.4-5.9 3.4 1.5-6.4-5-4.5 6.6-.6z"/>',
		filter: '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
		zap: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
		building:
			'<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4M8 6h.01M16 6h.01M12 6h.01M8 10h.01M16 10h.01M12 10h.01M8 14h.01M16 14h.01M12 14h.01"/>',
		'trending-up':
			'<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>'
	};

	/** @type {(keyof typeof ICONS)[]} */
	export const iconNames = /** @type {any} */ (Object.keys(ICONS));
</script>

<script>
	/**
	 * A small stroked icon set for marketing content (feature lists, bento
	 * cards, pricing bullets). Deliberately distinct from the tiny filled
	 * chrome icons hand-inlined in Alert/Modal/ToastContainer — those are
	 * UI-chrome glyphs, not content icons, and stay as they are.
	 *
	 * @type {{ name: keyof typeof ICONS, class?: string }}
	 */
	let { name, class: className = 'size-6' } = $props();
</script>

<svg
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width="1.5"
	stroke-linecap="round"
	stroke-linejoin="round"
	aria-hidden="true"
	class={className}
>
	<!-- ICONS is a hardcoded module-level constant above, never user input. -->
	<!-- eslint-disable-next-line svelte/no-at-html-tags -->
	{@html ICONS[name] ?? ''}
</svg>
