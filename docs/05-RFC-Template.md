---
title: RFC Template
created: 2026-08-11
project: NOVA
type: template
tags: [rfc, process, architecture]
---

# RFC: [Short Descriptive Title]

> [!info] Instructions
> Copy this template to `/08-RFCs/YYYY-MM-DD-title.md` when proposing a major change to NOVA's architecture, domain, or infrastructure.

## 1. Problem Statement

_What exact problem are we trying to solve? (e.g., "Nextcloud WebDAV sync is causing timeout errors during bulk media uploads from salons.")_

## 2. Background / Context

_Why does this problem exist? What is the current state?_

## 3. Proposed Solution

_Describe the technical design. Include Mermaid diagrams if helpful._

## 4. Alternative Solutions

_What else did we consider? (e.g., "Using AWS S3 instead of local Nextcloud", "Writing a custom Go upload service")._

## 5. Decision & Rationale

_Why is the proposed solution the best choice for NOVA right now?_

## 6. Impact

_How does this affect the DDD Domain, FastAPI endpoints, Local AI context limits, or Infrastructure?_

## 7. Migration / Rollout Plan

_How do we implement this safely without downtime?_

## 8. Risks & Trade-offs

_What are the drawbacks? (e.g., "Increases load on the Threadripper CPU during thumbnail generation")._

## 9. Open Questions

_What do we still need to figure out?_
