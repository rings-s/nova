import { defineConfig, minimal2023Preset } from '@vite-pwa/assets-generator/config';

/**
 * The installed app's icons, generated from one image at build time (and on
 * request under `vite dev`) by `SvelteKitPWA({ pwaAssets })` in vite.config.js:
 * 64/192/512 px, a 512 px maskable icon, the 180 px apple-touch-icon and
 * favicon.ico. Nothing generated is committed; replacing the image is the
 * whole change. A square source of 512 px or more (or an SVG) keeps them sharp.
 */
export default defineConfig({
	headLinkOptions: { preset: '2023' },
	preset: minimal2023Preset,
	images: ['static/Logo.png']
});
