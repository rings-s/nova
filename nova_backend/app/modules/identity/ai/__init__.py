# Reserved for future PydanticAI tool bindings scoped to the tenants module.
#
# Per project constraints: AI agents must call controlled application/domain
# tools (e.g. the commands/queries in this module) rather than touching the
# database directly, and must never be the source of truth for bookings,
# availability, payments, tickets, or queue order. No AI code lives here yet.
