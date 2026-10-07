import tailwindcss from '@tailwindcss/vite';
import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
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
			})
		]
	};
});
