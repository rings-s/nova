/**
 * Light/dark theme, explicit and persisted — rather than the OS-preference-
 * only mode this app started with. `src/app.html` sets the `.dark` class on
 * `<html>` synchronously before first paint (same resolution logic as
 * `loadInitial` below, duplicated there deliberately since it must run
 * before any JS module loads, to avoid a flash of the wrong theme); this
 * store keeps that class in sync afterward and persists explicit choices.
 */
import { browser } from '$app/environment';

const STORAGE_KEY = 'nova.theme';

function systemPrefersDark() {
	return browser && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

/** @returns {'light'|'dark'} */
function loadInitial() {
	if (!browser) return 'light';
	try {
		const stored = localStorage.getItem(STORAGE_KEY);
		if (stored === 'light' || stored === 'dark') return stored;
	} catch {
		// Storage unavailable (private mode, quota) — fall through to system.
	}
	return systemPrefersDark() ? 'dark' : 'light';
}

/** @param {'light'|'dark'} value */
function apply(value) {
	if (!browser) return;
	document.documentElement.classList.toggle('dark', value === 'dark');
	try {
		localStorage.setItem(STORAGE_KEY, value);
	} catch {
		// Theme still applies for the rest of this tab's session.
	}
}

let theme = $state(loadInitial());

// Apply the resolved theme as soon as this module loads. `app.html` may set
// the class before first paint too; this makes the stored choice take
// effect even when it doesn't.
if (browser) document.documentElement.classList.toggle('dark', theme === 'dark');

export const themeStore = {
	get value() {
		return theme;
	},
	get isDark() {
		return theme === 'dark';
	},
	/** @param {'light'|'dark'} value */
	set(value) {
		theme = value;
		apply(value);
	},
	toggle() {
		theme = theme === 'dark' ? 'light' : 'dark';
		apply(theme);
	}
};
