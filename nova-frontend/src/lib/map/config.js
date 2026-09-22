/**
 * Map configuration. Leaflet draws the map in the browser and OpenStreetMap
 * supplies the tiles, so the backend only ever deals in coordinates (ADR-0012).
 */
import { env } from '$env/dynamic/public';

/**
 * Where tiles come from. Defaults to OpenStreetMap's own server, which is right
 * for development and light use. Its usage policy
 * (https://operations.osmfoundation.org/policies/tiles/) rules out heavy
 * production traffic, so point `PUBLIC_MAP_TILE_URL` at a hosted or
 * self-hosted tile server before launch. Any `{z}/{x}/{y}` template works.
 */
export const TILE_URL = env.PUBLIC_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

/**
 * Credit shown on the map. OpenStreetMap's data licence (ODbL) requires it
 * whichever server the tiles come from; set `PUBLIC_MAP_ATTRIBUTION` when a
 * different tile provider asks for its own credit as well.
 */
export const TILE_ATTRIBUTION =
	env.PUBLIC_MAP_ATTRIBUTION ||
	'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

/** Standard OSM tiles are served up to zoom 19. */
export const MAX_ZOOM = 19;

/**
 * The view before anything is plotted: centred on the Gulf, wide enough to
 * hold the whole GCC. It is what an empty result set leaves on screen.
 * @type {[number, number]}
 */
export const DEFAULT_CENTER = [24.5, 48];
export const DEFAULT_ZOOM = 5;

/**
 * The closest `fitBounds` will zoom. A lone pin would otherwise fill the map
 * with one street; this keeps the surrounding district in frame.
 */
export const FIT_MAX_ZOOM = 15;

/** How close the map opens on a city an owner typed. District level. */
export const CITY_ZOOM = 12;

/** How close it goes to a pin that has been placed or found. Street level. */
export const PICK_ZOOM = 17;
