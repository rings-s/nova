"""ai_agents · the tools — thin wrappers over application services (docs/13 section 4).

Every tool is a translation: arguments in, one service call, a small JSON-able
dict out. There is no business logic here. A rule implemented in a tool would
be a rule the AI path enforces and the HTTP path does not.

Four things happen around every call, in `_run`:

  1. the allowlist is checked again. The runtime only registers allowed tools,
     so this catches a wiring mistake;
  2. the call is time-boxed (docs/10 section 12);
  3. a domain error becomes a refusal the model can relay, instead of ending
     the turn (docs/13 section 11);
  4. every number in the result is recorded as grounded for this turn, and the
     call is logged with session, tenant, tool and outcome (docs/10 section 2).

A tool that needs a service opens its own unit of work (`AgentDeps.services`):
a short transaction scoped to the tenant, committed when the tool returns and
rolled back when it raises or times out. Nothing holds a connection, or the
advisory lock a hold or a queue join takes, while the model thinks — and a
write is real the moment its tool returns. What a write produced for the client
(a hold and its token, a place in a queue) is recorded in `TurnArtifacts` only
after that commit.

Customer-facing tools act only on what the caller could reach over HTTP: each
one that names a booking, payment or queue entry runs the same per-row guard its
route runs. Owner-facing tools work on the one business the request named.
"""

from app.modules.ai_agents.tools.accountant import AccountantTools
from app.modules.ai_agents.tools.analyst import AnalystTools
from app.modules.ai_agents.tools.base import (
    BookedTicket,
    HeldSlot,
    PendingCancellation,
    QueuePlace,
    decode_offers,
    encode_offers,
)
from app.modules.ai_agents.tools.customer_service import CustomerServiceTools
from app.modules.ai_agents.tools.marketplace import MarketplaceTools
from app.modules.ai_agents.tools.receptionist import ReceptionistTools


class AgentToolkit(
    ReceptionistTools,
    MarketplaceTools,
    CustomerServiceTools,
    AccountantTools,
    AnalystTools,
):
    """Every tool, one file per agent. `for_agent` hands the model only the ones
    its `AgentSpec.tools` lists."""


__all__ = [
    "AgentToolkit",
    "BookedTicket",
    "HeldSlot",
    "PendingCancellation",
    "QueuePlace",
    "decode_offers",
    "encode_offers",
]
