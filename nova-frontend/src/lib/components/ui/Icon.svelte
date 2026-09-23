<script module>
	/**
	 * @typedef {'calendar'|'chat-bubble'|'users'|'chart-bar'|'credit-card'|'shield-check'|'globe'|'sparkles'|'check'|'chevron-left'|'chevron-right'|'arrow-right'|'x'|'user-check'|'phone'|'search'|'clock'|'map-pin'|'star'|'filter'|'zap'|'building'|'trending-up'|'sun'|'moon'|'menu'|'log-out'|'home'|'inbox'|'plus'|'chevron-down'|'receipt'|'settings'|'layers'|'arrow-up-right'|'user'|'panel-left'|'info'|'lock'|'table'|'arrow-up'|'arrow-down'|'minus'} IconName
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
			'<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
		sun: '<circle cx="12" cy="12" r="4.5"/><path d="M12 2.5v2.5M12 19v2.5M4.6 4.6l1.8 1.8M17.6 17.6l1.8 1.8M2.5 12h2.5M19 12h2.5M4.6 19.4l1.8-1.8M17.6 6.4l1.8-1.8"/>',
		moon: '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z"/>',
		menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
		'log-out':
			'<path d="M14.5 4.5h3a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-3M10 16.5 5.5 12 10 7.5M5.5 12h10"/>',
		home: '<path d="M4 10.5 12 4l8 6.5V19a1.5 1.5 0 0 1-1.5 1.5H15v-6H9v6H5.5A1.5 1.5 0 0 1 4 19z"/>',
		inbox:
			'<path d="M3.5 13.5h4.3l1.4 2.5h5.6l1.4-2.5h4.3M5.2 6.2 3.5 13.5v4A2.5 2.5 0 0 0 6 20h12a2.5 2.5 0 0 0 2.5-2.5v-4l-1.7-7.3A2.5 2.5 0 0 0 16.4 4H7.6a2.5 2.5 0 0 0-2.4 2.2z"/>',
		plus: '<path d="M12 5v14M5 12h14"/>',
		lock: '<rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
		table: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M3.5 9.5h17M3.5 14.5h17M10 9.5v10"/>',
		'arrow-up': '<path d="M12 19V5M5.5 11.5 12 5l6.5 6.5"/>',
		'arrow-down': '<path d="M12 5v14M5.5 12.5 12 19l6.5-6.5"/>',
		minus: '<path d="M5 12h14"/>',
		'chevron-down': '<path d="M6 9.5l6 6 6-6"/>',
		receipt:
			'<path d="M6 3.5h12v17l-2.5-1.5-2 1.5-1.5-1.5-1.5 1.5-2-1.5L6 20.5z"/><path d="M9 8h6M9 11.5h6M9 15h3.5"/>',
		settings:
			'<circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 3h-4l-.5 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7 7 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 21h4l.5-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.07-.4.1-.8.1-1.2z"/>',
		layers: '<path d="M12 3.5 21 8l-9 4.5L3 8z"/><path d="m3 12 9 4.5 9-4.5M3 16l9 4.5 9-4.5"/>',
		'arrow-up-right': '<path d="M7 17 17 7M8.5 7H17v8.5"/>',
		user: '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6"/>',
		info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 7.8v.2"/>',
		'panel-left': '<rect x="3.5" y="4" width="17" height="16" rx="2"/><path d="M9.5 4v16"/>'
	};

	/** @type {(keyof typeof ICONS)[]} */
	export const iconNames = /** @type {any} */ (Object.keys(ICONS));
</script>

<script>
	/**
	 * The app's one stroked icon set: navigation, content (feature lists, bento
	 * cards, pricing bullets) and inline action icons. Deliberately distinct from the tiny filled
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
	class={`shrink-0 ${className}`}
>
	<!-- ICONS is a hardcoded module-level constant above, never user input. -->
	<!-- eslint-disable-next-line svelte/no-at-html-tags -->
	{@html ICONS[name] ?? ''}
</svg>
