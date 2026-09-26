---
title: NOVA Vault Index
created: 2026-08-11
project: NOVA
type: index
status: index
tags: [index, nova, map]
aliases: [Home, Map of Content]
---

# NOVA Platform — Map of Content

> [!abstract] System Overview
> NOVA is an AI-powered, multi-vertical booking and operations platform.
> This vault documents the architecture, domain model, and infrastructure for the NOVA platform, currently targeting the Beauty/Wellness vertical, built on a **Local-First AI & Infrastructure** model.

> [!info] How to read these docs
> Each doc's frontmatter has a `status`:
>
> - **current**: kept in step with the code. Start here.
> - **design**: the plan, written before or while the code was built. The code may differ;
>   "Implemented differences" callouts mark the known gaps, and the code wins where they disagree.
> - **reference**: lookup tables that a test holds to the code (docs/15).
>
> `verified: <date>` is the last day the whole doc was checked against the code; no date means
> it has not been. The ADRs in `docs/decisions/` record decisions and carry their own status.
> `tests/test_doc_references.py` fails the build when a doc names a file that no longer exists.

## 🧭 Navigation

### 1. Architecture & Infrastructure

- [[01-Architecture-System-Overview]] · _design_ - C4 Model, Data Flow, and System Boundaries
- [[12-Backend-Code-Walkthrough]] · **current** - 🎓 **Start here if you are new** — FastAPI basics, every file explained, worked example
- [[02-Backend-FastAPI-DDD-Structure]] · _design_ - Domain-Driven Design folder structure and rules
- `nova_backend/README.md` - **Live code map**: dependency rules, module anatomy, traced request
- `docs/decisions/` - ADRs 0001-0015 (monorepo, vertical slices, tenant isolation, bilingual,
  tests, API security baseline, completing the remaining contexts, booking-source attribution,
  billing money decisions, public discovery and marketplace attribution, business agents and
  analytics, maps with Leaflet and OpenStreetMap, business photos replacing Nextcloud media,
  verified reviews and rating ranking, agents that book with QR tickets)
- `nova-frontend/README.md` - The SvelteKit app: running it, checks, the API client, stores,
  English/Arabic i18n and design tokens

### 2. Domain & AI

- [[03-Domain-Core-Model]] · _design_ - Bounded Contexts, Aggregates, and Business Rules
- [[04-AI-Agents-and-PydanticAI]] · _design_ - Local LLM routing, PydanticAI tools, and Guardrails
- [[06-Domain-Models-and-Aggregates]] · _design_ - Entities, Value Objects, and Aggregate rules per module
- [[10-AI-Agent-Catalog]] · _design_ - Every agent, its single goal, tools, and guardrails
- [[13-Business-Agents-and-Analytics]] · **current** - Receptionist, customer service, accountant, analyst and
  business manager agents; the analytics context, its metrics, and the chart catalog

### 3. API & Persistence

- [[07-Pydantic-Schemas-and-API-Contracts]] · _design_ - Request/Response schemas and naming conventions
- [[08-Database-Models-and-Persistence]] · _design_ - SQLAlchemy models, PostgreSQL, and Redis rules
- [[15-API-Error-Codes]] · **reference** - Every error code the API sends, its HTTP status, and what a client
  should do about it (kept in sync by `tests/test_error_catalog.py`)

### 4. Commercial Model

- [[11-Pricing-and-Subscriptions]] · _design_ - Plans, marketplace commission, invoicing, and payouts

### 5. Standards & Processes

- [[05-RFC-Template]] - Request for Comments template for major architectural decisions
- [[09-Final-Definition-of-Project-Completion]] · _design_ - Acceptance criteria for a complete project

### 6. Security

- [[14-Threat-Model]] · **current** - Trust boundaries, STRIDE per boundary, the findings register, and testable
  security requirements

---

> [!tip] Quick Links
>
> - **API Docs:** `/docs` (FastAPI Swagger UI)
> - **Business photos:** `MEDIA_ROOT` on the API host (ADR-0013)
> - **Frontend (dev):** http://localhost:5173
> - **Network Ingress:** Cloudflare Zero Trust Dashboard
