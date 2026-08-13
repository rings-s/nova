# Glossary

| Term | Meaning |
|---|---|
| Tenant | A business on NOVA (e.g. a salon brand). Owns one or more branches. See [[tenants-and-branches|../domain/tenants-and-branches]]. |
| Branch | A physical location belonging to a tenant. Has its own timezone, phone, slug. |
| Vertical slice | A module owning its full stack (router → domain) for one business capability, not split across technical layers. See [[backend-architecture|../architecture/backend-architecture]]. |
| Tenant isolation | Guarantee that one tenant's data is never readable/writable through another tenant's scope. Enforced today at the repository layer — see [[0003-tenant-isolation-strategy|../decisions/0003-tenant-isolation-strategy]]. |
| Ticket | Virtual QR ticket issued to a customer for a booking or queue position. Not yet built. |
| Queue | Walk-in queue at a branch. Not yet built. |
| BSP | Business Solution Provider — the approved intermediary required to send WhatsApp Business Platform messages. Specific BSP is "to verify" — see [[whatsapp|../integrations/whatsapp]]. |
