---
title: NOVA Vault Index
created: 2026-08-11
project: NOVA
type: index
tags: [index, nova, map]
aliases: [Home, Map of Content]
---

# NOVA Platform — Map of Content

> [!abstract] System Overview
> NOVA is an AI-powered, multi-vertical booking and operations platform. 
> This vault documents the architecture, domain model, and infrastructure for the NOVA platform, currently targeting the Beauty/Wellness vertical, built on a **Local-First AI & Infrastructure** model.

## 🧭 Navigation

### 1. Architecture & Infrastructure
- [[01-Architecture-System-Overview]] - C4 Model, Data Flow, and System Boundaries
- [[12-Backend-Code-Walkthrough]] - 🎓 **Start here if you are new** — FastAPI basics, every file explained, worked example
- [[02-Backend-FastAPI-DDD-Structure]] - Domain-Driven Design folder structure and rules
- `nova_backend/README.md` - **Live code map**: dependency rules, module anatomy, traced request
- `docs/decisions/` - ADRs 0001-0011 (monorepo, vertical slices, tenant isolation, bilingual,
  tests, API security baseline, completing the remaining contexts, booking-source attribution,
  billing money decisions, public discovery and marketplace attribution, business agents and
  analytics)

### 2. Domain & AI
- [[03-Domain-Core-Model]] - Bounded Contexts, Aggregates, and Business Rules
- [[04-AI-Agents-and-PydanticAI]] - Local LLM routing, PydanticAI tools, and Guardrails
- [[06-Domain-Models-and-Aggregates]] - Entities, Value Objects, and Aggregate rules per module
- [[10-AI-Agent-Catalog]] - Every agent, its single goal, tools, and guardrails
- [[13-Business-Agents-and-Analytics]] - Receptionist, customer service, accountant, analyst and
  business manager agents; the analytics context, its metrics, and the chart catalog

### 3. API & Persistence
- [[07-Pydantic-Schemas-and-API-Contracts]] - Request/Response schemas and naming conventions
- [[08-Database-Models-and-Persistence]] - SQLAlchemy models, PostgreSQL, and Redis rules

### 4. Commercial Model
- [[11-Pricing-and-Subscriptions]] - Plans, marketplace commission, invoicing, and payouts

### 5. Standards & Processes
- [[05-RFC-Template]] - Request for Comments template for major architectural decisions
- [[09-Final-Definition-of-Project-Completion]] - Acceptance criteria for a complete project

### 6. Security
- [[14-Threat-Model]] - Trust boundaries, STRIDE per boundary, the findings register, and testable
  security requirements

---
> [!tip] Quick Links
>
> - **API Docs:** `/docs` (FastAPI Swagger UI)
> - **Media Storage:** Nextcloud Instance
> - **Network Ingress:** Cloudflare Zero Trust Dashboard