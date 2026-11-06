"""Bounded context: CALL_CENTER — Sara, the AI agent who answers the phone (ADR-0017).

Aggregates      PhoneLine (a Unifonic number ringing one business),
                Call (one phone call, inbound or a reminder Sara places)
Depends on      ai_agents (AiChatService: Sara thinks like the chat agents),
                booking, catalog, identity, billing — their SERVICES only
Status          implemented; the Unifonic field names are still to be checked
                against a live account (`integrations/voice/unifonic.py`)
Plan            ADR-0017, docs/13 section 4.6

NOVA owns Sara: the agent, her tools and every domain rule are NOVA's, through
`ai_agents`. Unifonic only carries the call, as a loop of webhook turns: it
asks what to say, and sends back what the caller said (as text) or pressed.

Public surface (what other modules may import):

    CallCenterService                    from .service
    build_call_center_service            from .dependencies (worker, webhooks)
    CALL_CENTER_FEATURE                  the plan feature, "ai_call_center"

Rules that live here rather than in the model:

    keypad              1 books the held time, 2 cancels the offered booking,
                        a 4-digit code verifies the caller (`domain.Call`)
    caller ID           finds the customer to book for; reading their bookings
                        needs the code sent to their WhatsApp
    signed links        a line's URL and each turn's URL are credentials,
                        because Unifonic sends no Authorization header
    reminders           voice consent (PDPL), daytime in the branch's timezone,
                        a daily cap, one call per booking
"""
