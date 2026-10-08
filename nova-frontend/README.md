# NOVA frontend

The web app for NOVA: the public marketplace, the customer pages (bookings, tickets, the
assistant), and the staff dashboard at `/app`. SvelteKit 2 with Svelte 5 runes, JavaScript with
JSDoc types (no TypeScript sources), Tailwind CSS 4, served by `adapter-node`. English and Arabic,
right-to-left included.

## Run it

From the repository root, `make dev` starts the frontend with everything it talks to. Open
[localhost:5173](http://localhost:5173). Vite reloads on save; the source is bind-mounted into the
container.

Use `localhost`, not `127.0.0.1`: the API accepts browser requests from `http://localhost:5173`
only.

To run the dev server on the host instead, stop the container's (`docker compose -f
infra/docker-compose.yml --env-file infra/.env stop frontend`), then from `nova-frontend/`:

```bash
pnpm install
echo 'PUBLIC_API_BASE_URL=http://localhost:8000' > .env
pnpm exec vite dev --port 5173
```

`pnpm run dev` listens on port 3000, which the API does not accept requests from.

## Check your work

From `nova-frontend/`:

| Command               | What it checks                                             |
| --------------------- | ---------------------------------------------------------- |
| `pnpm run check`      | Types, through `svelte-check` over the JSDoc               |
| `pnpm run lint`       | Prettier formatting and ESLint                             |
| `pnpm run format`     | Rewrites files with Prettier                               |
| `pnpm run i18n:check` | Fails on any `t('…')` string without an Arabic translation |
| `pnpm run i18n:audit` | Lists English still hard-coded in markup                   |

CI does not run these yet, so run them before you push.

## Where things are

```
src/
├── routes/
│   ├── +page.svelte, about/, pricing/, features/   marketing pages
│   ├── discover/          the marketplace and each business's storefront
│   ├── (auth)/            /login and /register
│   ├── bookings/          a customer's bookings and QR tickets
│   ├── app/               the staff dashboard (its own sidebar layout)
│   └── api/v1/[...path]/  an in-memory mock of the API, for `vite dev` only
└── lib/
    ├── api/               one file per backend module; every call goes through client.js
    ├── stores/            app-wide state: auth, tenant, business, access, theme, toast
    ├── components/ui/     the design-system primitives (Button, Card, Checkbox, …)
    ├── components/<area>/ components for one part of the app
    └── i18n/              t(), and the Arabic dictionaries in ar/*.js
```

## How it fits together

**Calling the API.** Every request goes through `http` in `src/lib/api/client.js`. It adds the
base URL, the bearer token and the tenant path, sends idempotency keys, refreshes an expired
token once and retries, and turns the backend's error envelope into an `ApiError`. Add a call to
the matching `src/lib/api/<module>.js` rather than calling `fetch` yourself.

**Which API.** `PUBLIC_API_BASE_URL` picks the backend. Empty, the app calls its own origin: under
`vite dev` that is the mock in `src/routes/api/v1/[...path]/+server.js`, and in a production build
it expects a reverse proxy to route `/api/v1` to the backend (the mock answers 404 there). The
variable is read at build time, so pass it to `docker build` as a build argument.

**State.** The stores in `src/lib/stores/*.svelte.js` are module-level `$state`, so any component
can import one directly; there is no provider to wrap.

**Permissions.** `accessStore` loads the caller's role and permissions for the current business
(`GET /tenants/{id}/memberships/me`) and hides what they cannot use. It only hides: the backend
checks every request itself. Never decide access from the token's claims (`utils/jwt.js` decodes
them for display only).

## Writing for two languages

Wrap every string a user sees in `t('English text', { params })` from `$lib/i18n/index.svelte.js`:
`tp()` for plurals, `m()` for strings kept in constants. The English text is the key. Add its
Arabic to the matching `src/lib/i18n/ar/*.js`, then run `pnpm run i18n:check`.

- Those dictionary files are JSON bodies, and Prettier ignores them, so scripts can merge into
  them. Keep them valid JSON: double quotes, no trailing comma.
- A backend error translates by its code: add `"error.<code>"` to `ar/errors.js`.
- The `nova_locale` cookie picks the language, else the browser's `Accept-Language`. The server
  sets `<html lang dir>`, so Arabic renders right-to-left from the first byte.
- Charts and maps stay left-to-right (`dir="ltr"`) in both languages.

## Styling

Use the semantic tokens defined in `src/routes/layout.css`: `bg-canvas`, `bg-surface`,
`border-line`, `text-fg` and their variants, `rounded-control|card|panel`,
`shadow-card|raised|overlay` and `focus-ring`. They switch with the theme, so you never write a
`dark:` pair. Use the primitives in `src/lib/components/ui` and their variants
(`<Button size="icon">`) rather than overriding their classes.

Maps use Leaflet with OpenStreetMap tiles (ADR-0012).

## End-to-end tests

The Playwright specs are `*.e2e.js` files next to the routes they test. They run against the dev
server `make dev` already has up, so start the stack first, then from `nova-frontend/`:

```bash
pnpm exec playwright test                # all specs, two at a time
pnpm exec playwright test src/routes/discover   # one folder
```

Most specs stub the API with `page.route`, so they need the frontend, not a seeded backend. Set
`E2E_BASE_URL` to run them against another address.

Keep scratch files, a one-off config included, **outside** `nova-frontend/`. Vite watches the
directory and reloads every open page when a file appears in it, including pages in the middle of a
test. That is why Playwright writes its results to the system temp directory.

## Adding a dependency

Install it inside the running container, then restart the container. The container's
`node_modules` is a Docker volume that rebuilding the image does not refresh, and the source is
bind-mounted, so `pnpm add` updates `package.json` and `pnpm-lock.yaml` in your checkout:

```bash
docker compose -f infra/docker-compose.yml --env-file infra/.env exec frontend pnpm add <package>
docker compose -f infra/docker-compose.yml --env-file infra/.env restart frontend
```

After pulling someone else's dependency change, run the same with `pnpm install --frozen-lockfile`.

## Production build

```bash
docker build --build-arg PUBLIC_API_BASE_URL=https://api.example.com -t nova-frontend nova-frontend
```

The image runs `node build` on port 3000. Leave `PUBLIC_API_BASE_URL` empty when a reverse proxy
serves the app and the API on one origin.
