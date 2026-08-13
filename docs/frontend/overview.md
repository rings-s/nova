# Frontend Overview

SvelteKit + Svelte 5 (runes) + TypeScript, `@sveltejs/adapter-node` (self-hosted, not a
platform adapter — see [[../architecture/tech-stack]]).

## Layout

```
frontend/src/
├── app.html            — %lang%/%dir% placeholders filled by hooks.server.ts
├── hooks.server.ts      — resolves locale (cookie → Accept-Language → default)
├── lib/
│   ├── api/             — client.ts (thin fetch wrapper), types.ts (hand-kept DTOs)
│   └── i18n/             — en.json/ar.json + index.ts helpers, see i18n-rtl.md
└── routes/
    ├── +layout.server.ts — exposes resolved locale as page data
    ├── +layout.svelte
    ├── +page.svelte      — landing placeholder
    └── health/+page.svelte — calls backend /health, proves the API client end-to-end
```

## API client

`lib/api/client.ts` wraps `fetch` against `PUBLIC_API_BASE_URL` (from `.env`, see
`.env.example`). `lib/api/types.ts` holds DTOs hand-kept in sync with
`backend/app/modules/*/schemas.py` — revisit with an OpenAPI-generated client once the API
surface is large enough to justify the tooling.

## Locale-aware rendering

Pages read the active locale via SvelteKit's `page.data.locale` (from `$app/state`), **not** a
client-only store fed by `$effect` — `$effect` doesn't run during SSR, so a store-only approach
renders the wrong language on first paint in non-default locales. See [[i18n-rtl]].

## PWA

`static/manifest.webmanifest` is a placeholder (no icons yet, no service worker). Real offline
support/caching strategy is a separate, not-yet-started task.
