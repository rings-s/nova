# NOVA Frontend

SvelteKit + Svelte 5 + TypeScript PWA for the NOVA customer/business/provider experience.

## Developing

```sh
pnpm install
cp .env.example .env   # set PUBLIC_API_BASE_URL to the running backend
pnpm run dev
```

## Checking and building

```sh
pnpm run check   # svelte-check
pnpm run build   # production build via @sveltejs/adapter-node
pnpm run preview
```

## Layout

- `src/lib/api/` — thin fetch client + hand-maintained DTOs mirroring backend Pydantic schemas
- `src/lib/i18n/` — English/Arabic message dictionaries (see `docs/frontend/i18n-rtl.md`)
- `src/hooks.server.ts` + `src/routes/+layout.server.ts` — resolves locale from cookie/`Accept-Language`/`?locale=`, drives `<html lang dir>` for correct RTL on first paint
- `src/routes/health/` — calls the backend `/health` endpoint, demonstrating the API client end-to-end
