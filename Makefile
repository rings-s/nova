COMPOSE = docker compose -f infra/docker-compose.yml --env-file infra/.env
BACKEND = cd nova_backend && uv run
# `migrate`, `revision` and `test` need the schema owner, so they run in a
# one-off `tools` container. `backend` and `worker` never hold those credentials.
TOOLS = $(COMPOSE) run --rm tools

.PHONY: help dev down logs tunnel migrate migrate-check revision db-app-role backup restore-check superuser test test-local lint fmt typecheck check worker image

help:
	@echo "Docker (full stack):"
	@echo "  make dev        start postgres, redis, backend, worker, frontend"
	@echo "                  (migrations run first, in a one-shot container)"
	@echo "  make down       stop everything"
	@echo "  make logs       tail backend logs"
	@echo "  make tunnel     start with the Cloudflare tunnel profile"
	@echo "  make migrate    re-apply migrations in a one-off tools container"
	@echo "  make migrate-check  fail if the models changed without a migration (alembic check)"
	@echo "  make db-app-role  give nova_app its login on a volume older than that role"
	@echo "  make backup     dump the database now into the backup volume"
	@echo "  make restore-check  restore the newest dump into a scratch database and look at it"
	@echo "  make superuser email=you@example.com  make an account a NOVA administrator"
	@echo "                  (add revoke=1 to take it away); it edits service categories"
	@echo "  make test       run the suite in a one-off tools container"
	@echo "  make image      build the production image (the runtime target)"
	@echo ""
	@echo "Local (uv, needs postgres/redis on localhost):"
	@echo "  make test-local run the suite against localhost"
	@echo "  make lint / fmt / typecheck / check"

# Copies the example and fills each blank secret with 32 random bytes as hex, so
# no checkout shares a credential with another, or with this public repository.
# The temporary names match `.env.*.local` in .gitignore.
infra/.env:
	@set -e; \
	cp infra/.env.example infra/.env.tmp.local; \
	for key in POSTGRES_PASSWORD POSTGRES_APP_PASSWORD REDIS_PASSWORD SECRET_KEY; do \
		value=$$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n'); \
		awk -v key="$$key" -v value="$$value" '$$0 == key "=" { $$0 = key "=" value } { print }' \
			infra/.env.tmp.local > infra/.env.next.local; \
		mv infra/.env.next.local infra/.env.tmp.local; \
	done; \
	chmod 600 infra/.env.tmp.local; \
	mv infra/.env.tmp.local infra/.env; \
	echo "Created infra/.env with freshly generated secrets."

dev: infra/.env
	$(COMPOSE) up --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f backend

tunnel: infra/.env
	$(COMPOSE) --profile tunnel up --build

migrate:
	$(TOOLS) uv run alembic upgrade head

# CI runs this after `alembic upgrade head`: models and migrations must agree.
migrate-check:
	$(TOOLS) uv run alembic check

revision:
	@test -n "$(m)" || (echo "usage: make revision m=\"add_something\"" && exit 1)
	$(TOOLS) uv run alembic revision --autogenerate -m "$(m)"

# A new volume gets the `nova_app` login from infra/postgres/initdb. A volume
# initialised before that script existed needs this once; it is safe to re-run.
db-app-role:
	$(COMPOSE) exec postgres /docker-entrypoint-initdb.d/20-create-app-role.sh

# One dump now. The scheduled loop is the `backup` profile; see infra/backup/README.md.
backup:
	$(COMPOSE) --profile backup run --rm backup bash /opt/backup/backup.sh

# The restore drill: newest dump into a scratch database, a few counts, dropped.
restore-check:
	$(COMPOSE) --profile backup run --rm backup bash /opt/backup/restore-check.sh

# The only way to grant `users.is_superuser`: there is deliberately no API for
# it. Run as the schema owner inside the postgres container; the email is
# passed as a psql variable, never spliced into the SQL.
superuser:
	@test -n "$(email)" || { echo 'usage: make superuser email=you@example.com [revoke=1]'; exit 1; }
	@echo "UPDATE users SET is_superuser = $(if $(revoke),false,true) WHERE lower(email) = lower(:'email') RETURNING email, is_superuser;" \
	  | $(COMPOSE) exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -v email="$$1"' sh '$(email)'

worker:
	$(COMPOSE) exec backend uv run arq app.worker.arq_worker.WorkerSettings

test:
	$(TOOLS) uv run pytest

# The production image: no uv, no dev dependencies, non-root, migrations left
# to a deliberate step. `make dev` builds the `dev` target instead.
# `make image EXTRAS=ai` bakes in PydanticAI for the agents (docs/13).
image:
	docker build --target runtime \
		--build-arg UID=$$(id -u) --build-arg GID=$$(id -g) \
		--build-arg EXTRAS=$(EXTRAS) \
		-t nova-backend:latest nova_backend

# --- Local targets. These run against the host, not the containers, so they
#     work without Docker as long as postgres/redis are reachable. Lint, format
#     and typecheck need neither.
test-local:
	$(BACKEND) pytest

lint:
	$(BACKEND) ruff check app tests

fmt:
	$(BACKEND) ruff format app tests

typecheck:
	$(BACKEND) mypy app

# What CI runs, minus the database jobs. Settings needs these three to load,
# and assembling the app connects to nothing, so placeholders do (as in CI);
# values already in the environment win.
check: lint typecheck
	cd nova_backend && \
	DATABASE_URL=$${DATABASE_URL:-postgresql+asyncpg://check:check@localhost/check} \
	REDIS_URL=$${REDIS_URL:-redis://localhost:6379/0} \
	SECRET_KEY=$${SECRET_KEY:-make-check-not-a-real-secret} \
	ENV=$${ENV:-test} \
	uv run python -c "from app.main import create_app; create_app()"
