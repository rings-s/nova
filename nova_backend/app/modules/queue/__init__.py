"""Bounded context: QUEUE — walk-ins and QR check-in.

Aggregates      Queue, QueueEntry, Ticket
Tables          queues, queue_entries, tickets
Depends on      identity, catalog, booking
Status          implemented

Domain style: RICH entities. `QueueEntry` has a lifecycle
(waiting -> called -> checked_in -> in_service -> completed, with missed and
cancelled as exits) and so does `Ticket`, so both earn entity classes the way
booking does.

The two rules this context exists to keep (docs/03 section 4, docs/06 section 5):

  1. Walk-ins and appointments share ONE provider timeline with different
     priority weights — not two parallel calendars. `domain.priority_key` maps
     both onto a single instant: an appointment sorts at its booked time, a
     walk-in at its arrival time plus a penalty. That penalty is the entire
     reason booking ahead means anything.

  2. A Ticket's QR payload carries a ticket id, a random token, and a
     signature — never a name, phone, or anything else about the person. The
     database stores only a *hash* of that token, so reading the tickets table
     does not let anyone check in as somebody else.

Public surface — what other modules may import:
    from app.modules.queue.service import QueueService
    from app.modules.queue.domain import QueueEntryStatus, TicketStatus, QueueEntryFact
    from app.modules.queue.events import CustomerCalled, TicketIssued

Internal — do not import from other modules:
    models.py, repository.py, dependencies.py, router.py

Ordering is derived, never stored: `position` is a monotonic join counter used
for audit and tie-breaking, while the order people are actually seen in comes
from `domain.order_queue`. There is deliberately no endpoint to reorder the
line by hand.
"""
