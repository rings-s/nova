COMPOSE = docker compose -f infra/docker-compose.yml --env-file infra/.env
BACKEND = cd nova_backend && uv run
# `migrate`, `revision` and `test` need the schema owner, so they run in a
# one-off `tools` container. `backend` and `worker` never hold those credentials.
TOOLS = $(COMPOSE) run --rm tools

.PHONY: help dev down logs tunnel migrate revision db-app-role test test-local lint fmt typecheck check worker image

help:
	@echo "Docker (full stack):"
	@echo "  make dev        start postgres, redis, backend, worker"
	@echo "                  (migrations run first, in a one-shot container)"
	@echo "  make down       stop everything"
	@echo "  make logs       tail backend logs"
	@echo "  make tunnel     start with the Cloudflare tunnel profile"
	@echo "  make migrate    re-apply migrations in a one-off tools container"
	@echo "  make db-app-role  give nova_app its login on a volume older than that role"
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

revision:
	@test -n "$(m)" || (echo "usage: make revision m=\"add_something\"" && exit 1)
	$(TOOLS) uv run alembic revision --autogenerate -m "$(m)"

# A new volume gets the `nova_app` login from infra/postgres/initdb. A volume
# initialised before that script existed needs this once; it is safe to re-run.
db-app-role:
	$(COMPOSE) exec postgres /docker-entrypoint-initdb.d/20-create-app-role.sh

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

# What CI runs, minus the database jobs.
check: lint typecheck
	$(BACKEND) python -c "from app.main import create_app; create_app()"
