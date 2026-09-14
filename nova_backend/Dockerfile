# syntax=docker/dockerfile:1

# NOVA backend image.
#
# Two targets from one file, sharing one dependency layer:
#
#   dev       source is bind-mounted, uvicorn reloads on save, dev dependencies
#             and `uv` are present so `make test` / `make migrate` work through
#             `docker compose exec`. This is what infra/docker-compose.yml uses.
#   runtime   the default target. Application code baked in, no `uv`, no dev
#             dependencies, no build tooling, non-root, healthchecked.
#
# Build the production image explicitly:
#     docker build -t nova-backend:latest nova_backend
# Build the dev image (compose does this for you):
#     docker build --target dev -t nova-backend:dev nova_backend

# Declared before the first FROM so every stage can re-declare and consume
# them. An ARG does not cross a FROM boundary: a stage that uses one without
# naming it again gets an empty string, silently.
ARG PYTHON_VERSION=3.13
ARG UID=1000
ARG GID=1000


# --- shared base ----------------------------------------------------------

FROM python:${PYTHON_VERSION}-slim AS base

# The virtualenv lives OUTSIDE /app, and that is the single most important line
# in this file. infra/docker-compose.yml bind-mounts the source tree over /app
# so edits reload without a rebuild, and a bind mount replaces the whole
# directory: a venv at uv's default `/app/.venv` is masked by whatever the
# developer happens to have on their host, or — on a clean checkout — re-synced
# from scratch into their working tree on every container start.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH=/opt/venv/bin:$PATH

# Resolve from the lock file only. A container that quietly upgrades a
# dependency because it re-resolved at startup is not reproducible.
ENV UV_FROZEN=1
ENV UV_COMPILE_BYTECODE=1

# Copy rather than hardlink: the uv cache and /opt/venv can land on different
# layers, where hardlinking fails.
ENV UV_LINK_MODE=copy

ENV PYTHONUNBUFFERED=1

# Build the environment against the interpreter this image already ships, and
# never fetch another. Left to itself uv picks the newest compatible Python and
# will download one to get it — `requires-python = ">=3.13"` matches 3.14 and
# 3.15 too. The `runtime` stage copies /opt/venv and nothing else, so a venv
# built against a downloaded interpreter would arrive there pointing at a path
# that does not exist. `never` also makes a missing interpreter fail the build
# loudly instead of silently changing the Python version.
ENV UV_PYTHON=/usr/local/bin/python3
ENV UV_PYTHON_DOWNLOADS=never

WORKDIR /app


# --- dependencies ---------------------------------------------------------

FROM base AS builder

# Pinned to the family that reads this uv.lock (`revision = 3`). An older uv
# cannot parse it; an unpinned one makes the build unreproducible.
RUN pip install --no-cache-dir "uv>=0.12.5,<0.13"

# Only the two files that determine the dependency set, so an application edit
# does not invalidate the expensive layer below.
COPY pyproject.toml uv.lock ./

# No `--no-install-project`: `[tool.uv] package = false` already means the
# project is never installed into the environment — `app` is imported from the
# working directory instead.
RUN uv sync --frozen --no-dev


# --- development ----------------------------------------------------------

FROM builder AS dev

ARG UID
ARG GID

# Test and lint tooling on top of the runtime dependency set.
RUN uv sync --frozen

# The container writes into the bind mount — `alembic revision --autogenerate`
# produces a migration file there — so its uid has to match the host's:
#     docker build --build-arg UID=$(id -u) --build-arg GID=$(id -g) ...
#
# Creation is tolerant because a host uid may collide with a Debian system
# account; USER and chown below are numeric, so the build succeeds either way
# and the name is only a convenience.
#
# /opt/venv is chowned so that adding a dependency and re-running `uv run`
# inside the container syncs, instead of failing on a root-owned tree.
RUN groupadd --gid ${GID} nova 2>/dev/null || true; \
    useradd --uid ${UID} --gid ${GID} --create-home nova 2>/dev/null || true; \
    mkdir -p /home/nova; \
    chown -R ${UID}:${GID} /opt/venv /app /home/nova

USER ${UID}:${GID}

# useradd may have been skipped on a uid collision, so do not rely on it having
# set these. `uv run` needs a writable cache directory.
ENV HOME=/home/nova

# Keeps container-written __pycache__ directories out of the developer's
# bind-mounted tree, where they would arrive owned by the container user. Set
# here rather than in `base` so it cannot interfere with the bytecode
# precompilation the sync layers above perform.
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Liveness, not readiness. `/health/ready` touches the database, and wiring a
# database blip to container health turns it into a restart loop — the split is
# deliberate, see app/main.py.
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request as r; r.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# `uvicorn` resolves straight off PATH rather than through `uv run`, so startup
# does not stop to revalidate the environment against the lock. `uv run` is
# still installed, for `docker compose exec`.
#
# --reload-dir confines the watcher to application code. Without it watchfiles
# walks the entire bind mount, including .git and the caches.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--reload-dir", "app"]


# --- production -----------------------------------------------------------

FROM base AS runtime

ARG UID
ARG GID

# Built from `base`, not `builder`: this image gets the finished environment
# and none of the tooling that produced it — no uv, no pip, no compiler. The
# console scripts' shebangs point at /opt/venv/bin/python, which symlinks to
# the base image's /usr/local/bin/python3.13 — which is why both stages must
# share the same base image, and why UV_PYTHON above is pinned to it.
COPY --from=builder /opt/venv /opt/venv

RUN groupadd --gid ${GID} nova 2>/dev/null || true; \
    useradd --uid ${UID} --gid ${GID} --create-home nova 2>/dev/null || true; \
    mkdir -p /home/nova && chown ${UID}:${GID} /home/nova

# Application code, filtered by .dockerignore.
COPY --chown=${UID}:${GID} . .

# /opt/venv stays root-owned: the runtime user reads it and never writes it.
USER ${UID}:${GID}

ENV HOME=/home/nova

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request as r; r.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# Migrations are NOT run here. Two replicas booting at once would race Alembic,
# and a schema change should be a deliberate step rather than a side effect of
# a deploy. infra/docker-compose.yml has a one-shot `migrate` service; a real
# deployment wants the equivalent job.
#
# --proxy-headers because ingress terminates TLS upstream (Cloudflare tunnel,
# docs/01), so without it every client IP logs as the tunnel's and the rate
# limiter buckets the whole world into one.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
