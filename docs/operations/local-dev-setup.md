# Local Dev Setup

## Option A — Docker Compose (recommended once verified in your environment)

```sh
cp infra/.env.example infra/.env   # edit as needed
make dev                            # docker compose up --build
make migrate                        # alembic upgrade head, inside the backend container
```

Backend: http://localhost:8000 (docs at `/docs`). Frontend: http://localhost:5173.

> This scaffold's `docker compose` stack was written but **not run** in the sandbox it was
> built in (no docker-group access there) — verify `make dev` actually brings up all five
> services cleanly in your real environment. See `infra/README.md`.

## Option B — Run backend/frontend directly (what was actually used to verify this scaffold)

Requires a local Postgres and Redis (or point at any reachable instance).

```sh
cd backend
uv sync
cp .env.example .env   # set DATABASE_URL/REDIS_URL to your local instances
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

```sh
cd frontend
corepack enable && corepack prepare pnpm@latest --activate
pnpm install
cp .env.example .env   # PUBLIC_API_BASE_URL should match the backend above
pnpm run dev
```

## Tests

```sh
cd backend
TEST_DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<host>/nova_test uv run pytest
```

See [[testing-strategy]] for why a real Postgres is required (not SQLite).
