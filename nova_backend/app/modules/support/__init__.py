"""Bounded context: SUPPORT — follow-ups a person owes a customer.

Aggregates      FollowUp
Tables          follow_ups
Depends on      identity (who to contact)
Status          implemented

When an AI agent cannot help and tells the customer that someone from the
business will get back to them, this is where that promise is kept. Without
it, "a staff member will follow up" was a sentence and nothing more: no person
was ever told.

A follow-up is opened by the agent's own turn, never by the model's words
alone:

    chat        `AiChatService` (ai_agents), when a customer's turn ends in a
                handoff at a business, once per conversation
    call        `CallCenterService` (call_center), when Sara promises a call
                back, once per call

Opening is idempotent per source: a conversation or a call that hands off
again updates its follow-up, and reopens it if staff had resolved it. Staff
see the open ones at `GET /follow-ups` and close each with `resolve`.

The contact (name, phone, email) is copied when the follow-up opens, because
the person who asked for help may have no customer record at this business
yet, and staff need a way to reach them either way.

Domain style: PURE FUNCTIONS. A follow-up is open or resolved, and the ORM
model is the entity.

Public surface — what other modules may import:
    from app.modules.support.service import SupportService, FollowUpContact
    from app.modules.support.domain import FollowUpSource, FollowUpReason

Internal — do not import from other modules:
    models.py, repository.py, dependencies.py, router.py
"""
