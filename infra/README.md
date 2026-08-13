# Infra

Local Docker Compose stack: `postgres`, `redis`, `backend` (FastAPI/uvicorn with reload),
`worker` (ARQ), `frontend` (SvelteKit dev server). Source is bind-mounted into `backend`/
`frontend`/`worker` for live reload — these images are dev images, not production builds.

WhatsApp BSP, Moyasar, Nextcloud, and Cloudflare Tunnel are **not** services in this compose
file: they're external systems the backend will call as adapters once credentials exist (see
`backend/app/integrations/` and `docs/integrations/`). Their env vars are reserved here but
unused.

## Usage

```sh
cp .env.example .env   # edit as needed
docker compose up --build
```

- Backend: http://localhost:8000 (docs at `/docs`, health at `/health`)
- Frontend: http://localhost:5173
- Apply migrations inside the running backend container:
  `docker compose exec backend uv run alembic upgrade head`

## Memory limits

Each service sets a conservative `mem_limit` (postgres 512m, redis 256m, backend 1g,
worker 512m, frontend 1g) as a reduced-memory fallback baseline for a 64GB-RAM host. Raise
these if running on the target 128GB workstation, especially once a local AI inference
service (Ollama or an OpenAI-compatible server) is added here — that service will need most
of the RTX 5090's 32GB VRAM and should get its own explicit, larger limit when it's wired in.

## Known gaps (not built yet)

- No local AI inference service (Ollama / OpenAI-compatible server) in this compose file yet.
- No Cloudflare Tunnel service — ingress is unauthenticated `localhost` ports for local dev only.
  Production/shared access must go through a Cloudflare Tunnel, never direct port exposure.
- `docker compose up` has not been run/verified in the environment this scaffold was built in
  (no docker-group access in that sandbox) — verify it in your real environment before relying
  on it.
