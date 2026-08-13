# Cloudflare Tunnel

**Not configured.** Deployment/infra concern, not an application-level adapter — the FastAPI
and SvelteKit apps have no code dependency on Cloudflare. See
`backend/app/integrations/tunnel/__init__.py` (notes only, no code) and
`infra/docker-compose.yml` (no tunnel service defined yet).

## Requirement

Public ingress must go through Cloudflare Tunnel — **no ports exposed directly to the
internet**. `infra/docker-compose.yml` currently publishes `localhost` ports for local dev only;
that's fine for development but must not be how anything is exposed publicly.

## To verify

- Tunnel configuration mechanism: `cloudflared` config file vs. dashboard-managed tunnel vs.
  Docker-based `cloudflared` sidecar in `infra/docker-compose.yml`.
- Which services get public hostnames (frontend only? backend API too, for webhooks from
  WhatsApp/Moyasar?).
- Whether Cloudflare Access (Zero Trust) should gate any internal-only paths.

Do not implement against assumed configuration — confirm the tunnel setup before deploying
anything beyond local dev.
