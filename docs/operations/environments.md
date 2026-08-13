# Environments

`Settings.env` (`backend/app/core/config.py`) is one of `local | test | staging | production`.
Only `local` and `test` exist in practice today — no staging/production deployment has been
built.

| Env | Purpose | DB | Notes |
|---|---|---|---|
| `local` | Day-to-day development | Local/compose Postgres | `DEBUG=true`, permissive CORS |
| `test` | Automated tests | Separate `*_test` database, real Postgres | See [[testing-strategy]] |
| `staging` | Not set up yet | — | **To verify**: hosting target, whether it's the same Docker Compose stack on different hardware or something else |
| `production` | Not set up yet | — | **To verify**: same questions as staging, plus Cloudflare Tunnel / TLS / backup strategy |

All config is environment-variable driven via `pydantic-settings` (`.env` files, never
committed — only `.env.example` templates are tracked). See
`backend/.env.example`, `frontend/.env.example`, `infra/.env.example`.
