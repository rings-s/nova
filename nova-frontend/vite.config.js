import os from 'node:os';
import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import { SvelteKitPWA } from '@vite-pwa/sveltekit';
import { defineConfig, loadEnv } from 'vite';

/**
 * The API's origin when it is not this one (PUBLIC_API_BASE_URL), else nothing.
 * @param {string} mode
 */
function apiOrigin(mode) {
	const base = loadEnv(mode, process.cwd(), 'PUBLIC_').PUBLIC_API_BASE_URL;
	try {
		return base ? [/** @type {`${string}:`} */ (new URL(base).origin)] : [];
	} catch {
		return [];
	}
}

export default defineConfig(({ mode }) => {
	const api = apiOrigin(mode);
	return {
		plugins: [
			tailwindcss(),
			sveltekit({
				compilerOptions: {
					// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
					runes: ({ filename }) =>
						filename.split(/[/\\]/).includes('node_modules') ? undefined : true
				},
				adapter: adapter(),
				// Tokens live in localStorage, so a script that runs here can read them.
				// Only our own scripts run: SvelteKit adds a nonce (or a hash, on a
				// prerendered page) to its inline boot script, and nothing else inline
				// executes. Styles stay 'unsafe-inline' because Svelte and Leaflet set
				// style attributes; a style cannot read a token.
				csp: {
					mode: 'auto',
					directives: {
						'default-src': ['self'],
						'script-src': ['self'],
						'style-src': ['self', 'unsafe-inline', 'https://fonts.googleapis.com'],
						'font-src': ['self', 'https://fonts.gstatic.com'],
						// Map tiles come from PUBLIC_MAP_TILE_URL, set at run time, so any
						// https image; business photos come from the API.
						'img-src': ['self', 'data:', 'blob:', 'https:', ...api],
						'media-src': ['self', 'blob:'],
						// Moyasar's Payment Form posts card details straight to its API.
						'connect-src': ['self', 'https://api.moyasar.com', ...api],
						'object-src': ['none'],
						'base-uri': ['self'],
						'form-action': ['self'],
						'frame-ancestors': ['none']
					}
				}
			}),
			// Installable app: a web manifest, icons from static/Logo.png
			// (pwa-assets.config.js) and a service worker that precaches only the
			// build's static files. Pages are rendered per request, with a CSP nonce
			// and the caller's data, so no HTML is cached and there is no offline
			// fallback page; `/api` is never touched.
			SvelteKitPWA({
				// On under `vite dev` too, so the browser offers to install it there.
				// The dev worker precaches one empty file (suppressWarnings) and caches
				// nothing else, so it never serves stale code. It is generated outside
				// this directory: a new file here full-reloads every open page.
				devOptions: {
					enabled: true,
					suppressWarnings: true,
					resolveTempFolder: () => path.join(os.tmpdir(), 'nova-pwa-dev')
				},
				// A new worker waits until every tab of the old one is closed, rather
				// than reloading a page someone is typing in.
				registerType: 'prompt',
				injectRegister: false,
				pwaAssets: { config: true, overrideManifestIcons: true },
				manifest: {
					id: '/',
					name: 'NOVA',
					short_name: 'NOVA',
					description:
						'GCC-focused AI booking and customer operations platform for wellness and beauty centers',
					start_url: '/',
					scope: '/',
					display: 'standalone',
					theme_color: '#e11d48',
					background_color: '#f8fafc'
				},
				workbox: {
					navigateFallback: null,
					globPatterns: ['client/**/*.{js,css,ico,png,svg,webp,woff2,webmanifest}'],
					cleanupOutdatedCaches: true
				}
			})
		]
	};
});
