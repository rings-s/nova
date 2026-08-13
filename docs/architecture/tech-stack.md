# Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Backend framework | FastAPI | Async-native, Pydantic-integrated, dependency injection built in. |
| Validation/settings | Pydantic v2 + pydantic-settings | Single validation model for API boundaries, config, and (later) AI structured outputs. |
| ORM | SQLAlchemy 2.0 (async) + asyncpg | Async end-to-end; 2.0's typed `Mapped[]` style keeps models close to plain Python. |
| Migrations | Alembic (async `env.py`) | Standard SQLAlchemy migration tool; autogenerate against `Base.metadata`. |
| DB | PostgreSQL | System of record; UUID PKs, `TIMESTAMPTZ`, JSONB available for future needs. |
| Cache/queue/locks | Redis | Backs ARQ and future rate-limiting/locking needs. |
| Background jobs | ARQ | Redis-based, async-native, simpler operationally than Celery for this scale. |
| Python packaging | uv | Fast, lockfile-based (`uv.lock`), single tool for venv + deps + running. |
| Frontend framework | SvelteKit + Svelte 5 | Runes-based reactivity, SSR for correct RTL/lang on first paint (see [[../frontend/i18n-rtl]]). |
| Frontend package manager | pnpm (via corepack) | Fast, disk-efficient. |
| Frontend adapter | `@sveltejs/adapter-node` | Self-hosted via Docker + Cloudflare Tunnel — not a platform `adapter-auto` would detect. |
| Local dev orchestration | Docker Compose | `infra/docker-compose.yml` — postgres, redis, backend, worker, frontend. |
| Public ingress | Cloudflare Tunnel | No ports exposed directly to the internet. **To verify**: exact tunnel/service config — see [[../integrations/cloudflare-tunnel]]. |
| Media storage | Nextcloud | Backend stores references only, not binaries, in Postgres. Not implemented yet — see [[../integrations/storage-nextcloud]]. |
| Payments | Moyasar | Not implemented yet — see [[../integrations/payments-moyasar]]. |
| WhatsApp | WhatsApp Business Platform via an approved BSP | Not implemented yet — see [[../integrations/whatsapp]]. |
| AI agents | PydanticAI, local model runtime (Ollama/OpenAI-compatible) | Not implemented yet — see [[../ai/future-ai-integration]]. |
