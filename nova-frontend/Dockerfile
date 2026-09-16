# syntax=docker/dockerfile:1

# NOVA frontend image.
#
# Two targets from one file, sharing one dependency layer:
#
#   dev       source is bind-mounted, `vite dev` reloads on save. This is what
#             infra/docker-compose.yml uses. node_modules is baked into the
#             image and kept out from under the bind mount by a named volume
#             (see infra/docker-compose.yml) — the same problem nova_backend's
#             Dockerfile solves with a venv outside /app, solved the Node way.
#   runtime   the default target. `adapter-node`'s build output plus only
#             `dependencies` (never `devDependencies`) installed, non-root,
#             healthchecked.
#
# Build the production image explicitly:
#     docker build -t nova-frontend:latest nova-frontend
# Build the dev image (compose does this for you):
#     docker build --target dev -t nova-frontend:dev nova-frontend

ARG NODE_VERSION=22
ARG UID=1000
ARG GID=1000


# --- shared base ------------------------------------------------------------

FROM node:${NODE_VERSION}-slim AS base

# Ships with Node >=16.9; pins pnpm to the version pnpm-lock.yaml was written
# with rather than whatever corepack would otherwise fetch.
RUN corepack enable

WORKDIR /app


# --- dependencies -------------------------------------------------------------

FROM base AS deps

# Only the files that determine the dependency set, so an application edit
# does not invalidate this layer.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile


# --- development --------------------------------------------------------------

FROM deps AS dev

ARG UID
ARG GID

# The container writes into the bind mount (Vite's own cache, `pnpm install`
# after a dependency edit), so its uid has to match the host's:
#     docker build --build-arg UID=$(id -u) --build-arg GID=$(id -g) ...
#
# Creation is tolerant because a host uid may collide with a Debian system
# account; USER and chown below are numeric, so the build succeeds either way
# and the name is only a convenience.
RUN groupadd --gid ${GID} nova 2>/dev/null || true; \
    usermod --uid ${UID} --gid ${GID} node 2>/dev/null || \
    useradd --uid ${UID} --gid ${GID} --create-home nova 2>/dev/null || true; \
    mkdir -p /home/nova; \
    chown -R ${UID}:${GID} /app /home/nova 2>/dev/null || true

USER ${UID}:${GID}
ENV HOME=/home/nova

EXPOSE 5173

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:5173/').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"]

# --host so the dev server accepts connections from outside the container,
# not just 127.0.0.1 inside it.
CMD ["pnpm", "exec", "vite", "dev", "--host", "0.0.0.0", "--port", "5173"]


# --- production -----------------------------------------------------------

FROM deps AS build

COPY . .
RUN pnpm exec vite build


FROM base AS runtime

ARG UID
ARG GID

COPY package.json pnpm-lock.yaml ./
# Only `dependencies` (d3-array, d3-scale, layerchart) — everything that
# builds the app (svelte, sveltekit, vite, tailwind, ...) is a devDependency
# and stays out of the runtime image.
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile --prod

COPY --from=build /app/build ./build

RUN groupadd --gid ${GID} nova 2>/dev/null || true; \
    usermod --uid ${UID} --gid ${GID} node 2>/dev/null || \
    useradd --uid ${UID} --gid ${GID} --create-home nova 2>/dev/null || true; \
    mkdir -p /home/nova && chown -R ${UID}:${GID} /app /home/nova 2>/dev/null || true

USER ${UID}:${GID}
ENV HOME=/home/nova
ENV NODE_ENV=production

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"]

CMD ["node", "build"]
