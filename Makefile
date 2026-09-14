COMPOSE = docker compose -f infra/docker-compose.yml --env-file infra/.env
BACKEND = cd nova_backend && uv run

.PHONY: help dev down logs tunnel migrate revision db-app-role test test-local lint fmt typecheck check worker image

help:
	@echo "Docker (full stack):"
	@echo "  make dev        start postgres, redis, backend, worker"
	@echo "                  (migrations run first, in a one-shot container)"
	@echo "  make down       stop everything"
	@echo "  make logs       tail backend logs"
	@echo "  make tunnel     start with the Cloudflare tunnel profile"
	@echo "  make migrate    re-apply migrations inside the backend container"
	@echo "  make db-app-role  give nova_app its login on a volume older than that role"
	@echo "  make test       run the suite inside the backend container"
	@echo "  make image      build the production image (the runtime target)"
	@echo ""
	@echo "Local (uv, needs postgres/redis on localhost):"
	@echo "  make test-local run the suite against localhost"
	@echo "  make lint / fmt / typecheck / check"

infra/.env:
	@test -f infra/.env || (cp infra/.env.example infra/.env && \
		echo "Created infra/.env from the example — review SECRET_KEY before deploying.")

dev: infra/.env
	$(COMPOSE) up --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f backend

tunnel: infra/.env
	$(COMPOSE) --profile tunnel up --build

migrate:
	$(COMPOSE) exec backend uv run alembic upgrade head

revision:
	@test -n "$(m)" || (echo "usage: make revision m=\"add_something\"" && exit 1)
	$(COMPOSE) exec backend uv run alembic revision --autogenerate -m "$(m)"

# A new volume gets the `nova_app` login from infra/postgres/initdb. A volume
# initialised before that script existed needs this once; it is safe to re-run.
db-app-role:
	$(COMPOSE) exec postgres /docker-entrypoint-initdb.d/20-create-app-role.sh

worker:
	$(COMPOSE) exec backend uv run arq app.worker.arq_worker.WorkerSettings

test:
	$(COMPOSE) exec backend uv run pytest

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
