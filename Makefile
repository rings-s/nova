COMPOSE = docker compose -f infra/docker-compose.yml --env-file infra/.env

.PHONY: dev down migrate test lint fmt

dev:
	$(COMPOSE) up --build

down:
	$(COMPOSE) down

migrate:
	$(COMPOSE) exec backend uv run alembic upgrade head

test:
	$(COMPOSE) exec backend uv run pytest

lint:
	$(COMPOSE) exec backend uv run ruff check app tests

fmt:
	$(COMPOSE) exec backend uv run ruff format app tests
