# 0012 — Maps: Leaflet, OpenStreetMap Tiles, a Viewport-Shaped Search, and an Owner-Set Pin

## Status

Accepted — 2026-09-21

## Context

A branch has had a `latitude` and `longitude` since the catalog split, and discovery has searched by
radius around a point (ADR-0010). Nothing drew a map. A customer browsing `/discover` saw a list of
cards with a "2.4 km away" on them and no way to see where the salons were relative to each other or
to where they were.

The stack has three constraints on the answer. It is a public, unauthenticated surface (ADR-0010),
so anything a business types and the map displays is untrusted. It is rate-limited per address, at
60 reads a minute shared across the discovery read routes (search, storefront and now the map). And
the frontend is SvelteKit, which renders on the server, where a map library that reads `window`
cannot run.

## Decision

### Leaflet draws, OpenStreetMap supplies the tiles, both in the browser

Leaflet 1.9 (`leaflet`, no wrapper library) with OpenStreetMap's raster tiles. The backend never
touches a tile and never calls a map provider: it stores coordinates and answers questions about
them. No API key, no vendor account, no per-request cost, and nothing about a customer's browsing
leaves the browser except the tile requests.

- The library is imported dynamically inside `onMount`, so it never loads on the server.
- Markers are `L.divIcon`s built from DOM nodes, not HTML strings, and carry the listing name only
  as a `title` property. A business names its own listing, so no popup or icon ever parses one.
- The map is its own stacking context (`isolate`). Leaflet's panes and controls use z-indexes
  from 200 to 1000, which would otherwise paint over the Quick View modal below `lg`, where
  nothing else contains it (from `lg` up the sticky wrapper is a stacking context already). An
  end-to-end test at phone width fails if `isolate` is removed.
- Tile URL and attribution come from `PUBLIC_MAP_TILE_URL` and `PUBLIC_MAP_ATTRIBUTION`, read at
  runtime, so changing provider is a deployment setting and not a code change.

### The backend gains a viewport filter and a GeoJSON view of the same search

- `bbox=west,south,east,north` on `GET /discovery/businesses`, in Leaflet's `toBBoxString()` order
  so a viewport goes through untouched. It is exact, so the database pages it like any other
  filter. With a radius, the two are intersected and the circle is still trimmed.
- `GET /discovery/map`: the same filters, returned as a GeoJSON FeatureCollection of located
  branches only, not paged, capped by `limit` (default 200, at most 500), with `truncated` set when
  the cap cut any off. A page of pins is a map with holes in it; the cap bounds the response
  instead. A feature's `properties` is `ListingCardOut` itself, so the map cannot expose more than
  a search result does (no phone numbers, ADR-0010).
- The route is `/discovery/map`, not `/discovery/businesses/map`: the latter would be captured by
  `/businesses/{slug}` and would shadow any business whose slug is "map".

### Owners set the pin

A branch appears on the map only if it has coordinates, and the catalog's create-location form
sent none. So the owner's side is part of this decision, not a follow-up:

- `PATCH /tenants/{tenant_id}/catalog/locations/{location_id}/position` takes `{latitude,
  longitude}`, both numbers or both null (which removes the pin). Both keys are required, so `{}` is
  a 422 and not a silent "clear". It is staff-only and rate-limited like every catalog write, is its
  own verb like the listing switch (it changes what a customer sees and nothing the branch runs on),
  and reuses the catalog's `validate_coordinates`, which refuses a half pair, an out-of-range
  value, and NaN.
- `LocationPicker` (Leaflet, in the "Add location" form and in a "Map position" dialog opened from
  each branch's card) places the pin by clicking the map, dragging the pin, using the device's
  location, or typing or pasting `24.7136, 46.6753`. The text field is not a fallback: a map is
  pointer-only, so the field is how a keyboard or screen-reader user places a pin at all. The form
  holds its submit button back while the field holds something that is not a position.
- Typing a known GCC city (English or Arabic, matched whole) moves the map there, from a small table
  in `lib/map/cities.js`, so placing a pin starts in the right district. Only a starting view: it is
  never saved or sent anywhere, and never moves a map that already has a pin.
- "Use my location" (`lib/map/geolocate.js`) asks the browser for a quick answer first (a cached fix
  is fine, GPS is not demanded) and then a precise one, for 27 seconds at most, and draws how
  accurate the fix is as a circle. A fix worse than one kilometre is not trusted with a pin: the map
  moves there and the owner is asked to click the exact spot, because a computer with no GPS is
  placed from its Wi-Fi or its IP address, and that can be the wrong neighbourhood or the wrong
  city. Taking over (a click, a drag, typing) cancels the search, so a late fix never moves a pin
  the owner placed. Every failure says what to try instead and quotes the browser's own error.
- The pin is optional. A branch with none is still bookable and still found by name or city; it is
  only absent from the map. Each card says which it is and links to the point on OpenStreetMap.

The GeoJSON is served as `application/json`, not the RFC 7946 media type `application/geo+json`.
FastAPI documents a route's error responses under that route's own media type, so a `geo+json`
route publishes its errors as `geo+json` while `core/error_handlers.py` always sends them as JSON,
and `tests/test_error_contract.py` exists to stop those two disagreeing. Nothing consuming this
endpoint dispatches on media type. If a third-party GeoJSON consumer ever does, the fix is
hand-written error documentation for that one route, not a looser contract test.

## Consequences

- **A branch is on the map only once its owner pins it.** Branches that existed before this change
  have no coordinates, and stay off the map until someone opens "Set on map" on each. Nothing
  backfills them, and nothing checks that a pin is plausible: an owner can place one anywhere on
  Earth, or beside the wrong building. It is the owner's own listing, so this is accepted, but it
  means the map is as accurate as the owners are.
- **Detecting the device depends on the browser's location provider, which NOVA cannot fix.** On
  the machine this was built on, Firefox failed instantly because GNOME's Location Services were
  switched off (`org.gnome.system.location enabled`), and headless Chrome and Chromium timed out.
  The picker says which failure it saw and always leaves the map and the coordinates field. An
  approximate fallback from the visitor's IP address was measured and not built: two free lookup
  services returned cities about 700 km apart (Riyadh and Medina) for the same connection, so it
  would sometimes send the map to the wrong city, and it would add a third party that sees the
  owner's address.
- **OpenStreetMap's tile server is for development and light use.** Its usage policy
  (https://operations.osmfoundation.org/policies/tiles/) rules out heavy production traffic. Before
  launch, point `PUBLIC_MAP_TILE_URL` at a hosted or self-hosted tile server. The attribution
  (`© OpenStreetMap contributors`) is required by the data licence whichever server is used.
- **Pins are not clustered.** Several branches in one city stack on top of each other at country
  zoom, and the one on top hides the rest. "Search this area" and zooming work around it;
  `leaflet.markercluster` is the fix if that proves too rough.
- **A search now costs up to two requests, not one.** The list and the map query separately.
  The pin request is debounced so typing does not double the traffic, but both draw on the same
  60-a-minute allowance per address.
- **The map is capped, and says so.** Past `limit` branches in view, `truncated` is true and the UI
  asks the customer to zoom in and search an area.

## Alternatives considered

- **Geocoding (OSM Nominatim) in the backend: turn a typed address into coordinates.** Not done.
  It sends business addresses to a third party, the public instance's usage policy is strict
  (about one request a second, and no autocomplete; check the current policy before relying on
  it), and `Location` has no address column to geocode from. The picker works
  without it (city table, device location, pasted coordinates), so it is a convenience to add
  later, and a separate decision because of the address-privacy and rate-limit points above.
- **PostGIS.** Not done. A bounding box on two indexable columns, then haversine on the rows that
  pass, is exact enough at city scale and needs no extension. It becomes worth it if radius search
  ever needs a real spatial index or polygon areas.
- **Google Maps or Mapbox.** Rejected: an API key, a billing account and a per-load cost, to draw
  pins that Leaflet draws for nothing.
- **`application/geo+json`.** Considered and reverted; see above.
