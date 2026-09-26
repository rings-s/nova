---
title: Final Definition of Project Completion
created: 2026-08-11
project: NOVA
type: process
status: design
tags: [completion, acceptance-criteria, scope]
---

# Final Definition of Project Completion

> [!important] Acceptance Criteria
> The project is complete when all of the following are true.

1. A business owner can create a business and location.
2. A business owner can add services, providers, schedules, and business photos.
3. A customer can discover a business and book a service.
4. Availability is deterministic and prevents double booking.
5. Payment or deposit flows work through a sandboxed Moyasar integration.
6. A virtual ticket with secure QR code is generated.
7. Walk-ins and appointments coexist in the queue.
8. Reception can scan QR tickets and check customers in.
9. WhatsApp notifications are sent for booking and queue events.
10. AI assistants can help customers and businesses through controlled tools.
11. AI does not bypass domain rules.
12. Business photos are re-encoded on upload and stored outside PostgreSQL (`MEDIA_ROOT`).
13. PostgreSQL stores photo metadata only (`business_photos`).
14. The backend runs locally using Docker.
15. Cloudflare Tunnel securely exposes the system.
16. PostgreSQL and Redis run reliably.
17. Local AI runs on the RTX 5090 with fallback behavior.
18. Tests cover booking, queue, payment, tenant isolation, and AI guardrails.
19. Documentation is complete and aligned with the codebase.
20. Backup and restore procedures work.

> [!note] Revised criteria
> Items 12 and 13 originally named Nextcloud. ADR-0013 removed Nextcloud and moved business photos
> into `catalog`, with files in the API's own image store. The intent is unchanged: binaries stay
> out of the database.
