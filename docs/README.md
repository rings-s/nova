# NOVA Documentation Vault

Obsidian-friendly Markdown. Open this `docs/` folder as an Obsidian vault to get backlinks and
graph view for free.

## Map

- [[vision|product/vision]] — what NOVA is and who it's for
- [[overview|architecture/overview]] — system context and module boundaries
- [[tenants-and-branches|domain/tenants-and-branches]] — the first vertical slice's domain model
- [[module-template|domain/module-template]] — how to build the next module
- [[tenants-api|api/tenants-api]] — the tenants module's HTTP surface
- [[local-dev-setup|operations/local-dev-setup]] — get it running
- `decisions/` — ADRs, one per non-obvious architectural choice

## Folder purpose

| Folder | Contains |
|---|---|
| `product/` | Vision, personas, glossary — what and why, not how |
| `domain/` | Business rules and models, independent of code layout |
| `architecture/` | System structure, module boundaries, tech choices |
| `api/` | HTTP surface per module |
| `ai/` | AI agent design and constraints (PydanticAI, tool boundaries) |
| `frontend/` | SvelteKit conventions, i18n/RTL |
| `integrations/` | External systems as adapters — WhatsApp, Moyasar, Nextcloud, Cloudflare |
| `operations/` | Running, testing, and environments |
| `decisions/` | ADRs — the *why* behind non-obvious choices |
| `legal/` | Compliance items flagged for legal review — no claims asserted |

Update docs in the same change as the code they describe.
