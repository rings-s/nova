# i18n and RTL

## Approach: hand-rolled, not Paraglide

Only English and Arabic are in scope today. A compiler-based i18n library (Paraglide/inlang)
buys compile-time type safety and per-locale code-splitting, at the cost of an extra build
dependency and a less transparent integration. For two locales and a small message set, a
flat JSON dictionary + a typed `t()` helper (`frontend/src/lib/i18n/index.ts`) is simpler to
reason about and fully under our control. **Revisit this if locale count or message volume
grows enough that hand-maintaining `en.json`/`ar.json` becomes the bottleneck.**

## How locale is resolved

1. `?locale=ar` query param (explicit switch) — highest priority, persisted to a cookie.
2. `locale` cookie (returning visitor).
3. `Accept-Language` header (first visit).
4. `en` (default).

Resolved once per request in `hooks.server.ts`, stored on `event.locals.locale`, exposed to
pages via `+layout.server.ts` → `page.data.locale`.

## Why SSR-driven, not a client store

`app.html` has `<html lang="%lang%" dir="%dir%">` placeholders, filled by
`hooks.server.ts`'s `transformPageChunk` — so the correct `dir="rtl"` is present in the very
first byte of HTML, no flash of wrong direction. Pages read `page.data.locale` (from
`$app/state`) directly for their own text content, which is populated synchronously during SSR.

An earlier version of this scaffold used a `writable()` store set via `$effect` in
`+layout.svelte` — that's a bug: `$effect` only runs after mount (client-side), so during SSR
the store still held its default value, meaning Arabic pages rendered with `dir="rtl"` but
**English text**. Fixed by reading `page.data.locale` directly instead. If you add client-only
interactive locale switching later, re-derive from `page.data`, don't reintroduce a
store-plus-effect for anything that must be correct on first paint.

## RTL styling

No RTL-specific CSS exists yet beyond the `dir` attribute (which flips default text direction
and some browser-native behavior). Component-level logical properties (`margin-inline-start`
etc. instead of `margin-left`) should be the default once real UI is built, so RTL doesn't need
a parallel stylesheet.
