# Local development image: installs deps, runs the Vite dev server against a
# bind-mounted source tree (see infra/docker-compose.yml). Not a production
# build — that would use `pnpm run build` + `node build` from adapter-node.
FROM node:22-slim

RUN corepack enable

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

EXPOSE 5173

CMD ["pnpm", "run", "dev", "--host", "0.0.0.0"]
