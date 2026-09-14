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
*What exact problem are we trying to solve? (e.g., "Nextcloud WebDAV sync is causing timeout errors during bulk media uploads from salons.")*

## 2. Background / Context
*Why does this problem exist? What is the current state?*

## 3. Proposed Solution
*Describe the technical design. Include Mermaid diagrams if helpful.*

## 4. Alternative Solutions
*What else did we consider? (e.g., "Using AWS S3 instead of local Nextcloud", "Writing a custom Go upload service").*

## 5. Decision & Rationale
*Why is the proposed solution the best choice for NOVA right now?*

## 6. Impact
*How does this affect the DDD Domain, FastAPI endpoints, Local AI context limits, or Infrastructure?*

## 7. Migration / Rollout Plan
*How do we implement this safely without downtime?*

## 8. Risks & Trade-offs
*What are the drawbacks? (e.g., "Increases load on the Threadripper CPU during thumbnail generation").*

## 9. Open Questions
*What do we still need to figure out?*