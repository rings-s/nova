"""ai_agents · DOMAIN layer — the guardrails.

Layer rule: stdlib and pydantic only. Must not import fastapi, sqlalchemy, or
an inference client.

docs/10 section 11 is explicit that "guardrails are code in `guardrails.py`,
not prompt text", and that is the design here. A prompt asking a model not to
leak phone numbers is a request; a regex that removes them before the model
ever sees them is a guarantee. Everything in this file is a pure function so it
can be tested exhaustively with no model, no database, and no network.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from uuid import UUID

from app.core.exceptions import DomainError

#: Phone numbers in the shapes NOVA actually handles: E.164, local GCC formats,
#: and spaced or hyphenated variants. Loose on purpose, which is why
#: `_mask_phone` also asks for a phone number's worth of digits.
_PHONE_PATTERN = re.compile(r"(?:\+?\d[\d\s\-().]{7,}\d)")
#: The fewest digits a GCC number has: a mobile's 5XXXXXXXX without its leading
#: zero. A shorter run the pattern catches is a price or a time range.
_MIN_PHONE_DIGITS = 9
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
#: Long digit runs that look like a card or IBAN. Deliberately aggressive:
#: masking a reference by accident costs little, leaking a PAN costs
#: everything.
_PAYMENT_REF_PATTERN = re.compile(r"\b(?:[A-Z]{2}\d{2}[A-Z0-9]{10,30}|\d{12,19})\b")

#: A booking, queue entry or payment id as a customer pastes it. Redaction
#: leaves it whole, and grounding ignores its hex fragments.
UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
#: 2026-09-20, 20/09/2026 or 20.09.26, in any digit system NOVA replies in. The
#: lookarounds stop a "date" being read out of the middle of a longer run, such
#: as a phone number written +966-50-123-4567.
_DATE_PATTERN = re.compile(
    r"(?<![\d+\-/.])"
    r"(?:(?P<year>\d{4})[-/.](?P<iso_month>\d{1,2})[-/.](?P<iso_day>\d{1,2})"
    r"|(?P<first>\d{1,2})[-/.](?P<second>\d{1,2})[-/.](?:\d{4}|\d{2}))"
    r"(?![\d\-/.])"
)


def _mask_phone(match: re.Match[str]) -> str:
    digits = sum(char.isdigit() for char in match.group(0))
    return "[phone]" if digits >= _MIN_PHONE_DIGITS else match.group(0)


def _is_plausible_date(match: re.Match[str]) -> bool:
    if match.group("year") is not None:
        month, day = int(match.group("iso_month")), int(match.group("iso_day"))
        return 1 <= month <= 12 and 1 <= day <= 31
    first, second = int(match.group("first")), int(match.group("second"))
    # Day first is the GCC way round, but a month-first date is still a date.
    return (1 <= first <= 31 and 1 <= second <= 12) or (1 <= first <= 12 and 1 <= second <= 31)


_REDACTIONS: tuple[tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]], ...] = (
    (_EMAIL_PATTERN, "[email]"),
    (_PAYMENT_REF_PATTERN, "[payment-ref]"),
    (_PHONE_PATTERN, _mask_phone),
)

#: Phrases that only ever appear when someone is trying to talk past the
#: system prompt. Matched case-insensitively against untrusted text.
_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", re.I),
    re.compile(r"disregard\s+(?:all\s+)?(?:previous|prior|your)\s+", re.I),
    re.compile(r"you\s+are\s+now\s+(?:a|an|the)\s+", re.I),
    re.compile(r"system\s*(?:prompt|message)\s*[:=]", re.I),
    re.compile(r"</?\s*(?:system|assistant|tool)\s*>", re.I),
    re.compile(r"\bdeveloper\s+mode\b", re.I),
    re.compile(r"reveal\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions)", re.I),
    # Direct tool invocation attempts written into message content.
    re.compile(r"\b(?:call|invoke|execute)\s+(?:the\s+)?tool\b", re.I),
    re.compile(r"\bconfirm_booking\b|\bcapture_payment\b|\brefund\b", re.I),
)

MAX_MESSAGE_LENGTH = 4000


class GuardrailViolation(StrEnum):
    TENANT_MISMATCH = "tenant_mismatch"
    TOOL_NOT_ALLOWED = "tool_not_allowed"
    WRITE_FORBIDDEN = "write_forbidden"
    OUTPUT_INVALID = "output_invalid"
    OWNER_ONLY = "owner_only"
    UNGROUNDED_NUMBERS = "ungrounded_numbers"
    PROPOSAL_REFUSED = "proposal_refused"


class GuardrailError(DomainError):
    """A refusal, not a fault.

    403 rather than 500: the agent was asked to do something it is structurally
    not permitted to do, and the caller should see that clearly.
    """

    status_code = 403
    code = "agent_guardrail"

    def __init__(self, violation: GuardrailViolation, detail: str) -> None:
        super().__init__(detail)
        self.violation = violation


@dataclass(frozen=True)
class SanitizedInput:
    """What the model is allowed to see, and what we noticed on the way."""

    text: str
    redacted: bool
    injection_detected: bool


def redact_pii(text: str) -> tuple[str, bool]:
    """Masks phone numbers, emails, and payment references.

    docs/10 section 11 requires this *pre-prompt*. Local inference does not make
    it optional: the text also ends up in prompt logs, traces, conversation
    memory, and any future fine-tuning set, and a masked value is one that
    cannot leak from any of them.

    Ids and plausible dates are set aside first, and redaction runs only on the
    text between them. A customer names the booking they need help with by its
    id and asks for a day by its date, and the loose phone pattern used to eat a
    quarter of all UUIDs and every ISO date.

    Order matters — emails are matched before phone numbers, because the digits
    in an address would otherwise be eaten by the phone pattern first.
    """
    pieces: list[str] = []
    cursor = 0
    for start, end in _protected_spans(text):
        if start < cursor:  # inside a span already set aside
            continue
        pieces += [_redact(text[cursor:start]), text[start:end]]
        cursor = end
    pieces.append(_redact(text[cursor:]))
    redacted = "".join(pieces)
    return redacted, redacted != text


def _protected_spans(text: str) -> list[tuple[int, int]]:
    spans = [match.span() for match in UUID_PATTERN.finditer(text)]
    spans += [match.span() for match in _DATE_PATTERN.finditer(text) if _is_plausible_date(match)]
    return sorted(spans)


def _redact(segment: str) -> str:
    for pattern, replacement in _REDACTIONS:
        segment = pattern.sub(replacement, segment)
    return segment


def detect_injection(text: str) -> bool:
    """Whether untrusted text is trying to issue instructions."""
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)


def sanitize_untrusted_text(text: str) -> SanitizedInput:
    """The single entry point for anything a human wrote.

    Applies to customer messages, review text, and business bios alike
    (docs/10 section 11: "untrusted text is never treated as instruction").
    Detected injection is not an error — the text is wrapped and passed through
    as *data*, because refusing outright would let anyone deny themselves
    service by quoting the wrong sentence at a chatbot.
    """
    trimmed = text.strip()[:MAX_MESSAGE_LENGTH]
    injection = detect_injection(trimmed)
    cleaned, redacted = redact_pii(trimmed)

    if injection:
        # Neutralised by framing, not deletion. The model is told this is
        # quoted user data; the tool allowlist is what actually stops it acting
        # on anything the text asks for.
        cleaned = f"<untrusted_user_text>\n{cleaned}\n</untrusted_user_text>"

    return SanitizedInput(text=cleaned, redacted=redacted, injection_detected=injection)


def assert_tool_allowed(tool_name: str, allowlist: frozenset[str]) -> None:
    """A tool outside the allowlist does not exist for that agent.

    Belt and braces: the agent definition only registers its own tools, so an
    unlisted tool is normally unreachable. This catches the case where a tool
    is registered on a shared agent by mistake.
    """
    if tool_name not in allowlist:
        raise GuardrailError(
            GuardrailViolation.TOOL_NOT_ALLOWED,
            f"The tool '{tool_name}' is not available to this agent.",
        )


def assert_tenant_matches(requested, scoped) -> None:
    """Tenant scoping, enforced at `AgentDeps` construction (docs/10 s11).

    The model never supplies a tenant id. If a request somehow carries one that
    disagrees with the authenticated scope, the turn is rejected *before* any
    inference happens — an agent that has already read the wrong salon's data
    cannot un-read it.
    """
    if requested is not None and requested != scoped:
        raise GuardrailError(
            GuardrailViolation.TENANT_MISMATCH,
            "The requested tenant does not match the authenticated session.",
        )


# --- owner-only agents (docs/10 section 4, docs/13 section 5.1) -------------

#: Agents that speak for the business rather than to its customers, and the
#: old names that resolve to them. A customer principal reaches every tenant on
#: the marketplace, so without this a customer could ask for a salon's revenue,
#: invoices and commission lines, figures the billing and analytics routes keep
#: behind `require_staff`.
OWNER_ONLY_AGENTS: frozenset[str] = frozenset(
    {
        "accountant_agent",
        "analyst_agent",
        "business_manager_agent",
        "billing_agent",
        "insights_agent",
    }
)


def assert_caller_may_use_agent(agent_name: str, *, caller_is_staff: bool) -> None:
    """Refuses an owner-only agent to anyone but staff, before the model runs."""
    if agent_name in OWNER_ONLY_AGENTS and not caller_is_staff:
        raise GuardrailError(
            GuardrailViolation.OWNER_ONLY,
            f"The agent '{agent_name}' is available to the business's staff only.",
        )


#: Statuses the booking agent may move a booking to. Confirmation is absent
#: deliberately and permanently (docs/10 section 5): only a verified payment
#: webhook confirms a booking, never a language model.
AGENT_ALLOWED_BOOKING_STATUSES: frozenset[str] = frozenset(
    {"draft", "pending_payment", "cancelled"}
)


def assert_agent_may_set_status(status: str) -> None:
    if status not in AGENT_ALLOWED_BOOKING_STATUSES:
        raise GuardrailError(
            GuardrailViolation.WRITE_FORBIDDEN,
            f"An agent may not move a booking to '{status}'. "
            "Confirmation belongs to the verified payment webhook.",
        )


# --- numeric grounding (docs/13 section 5.2) --------------------------------

#: Arabic-Indic and Extended Arabic-Indic digits, and the Arabic decimal,
#: thousands and percent signs, read as their Western forms.
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬٪", "01234567890123456789.,%")  # noqa: RUF001
_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|\d+(?:\.\d+)?%?")

#: Whole numbers this small usually carry structure rather than a claim ("the
#: top 3 services"). A deliberate, documented hole in the check.
SMALL_INTEGER_EXEMPTION = 10


@dataclass(frozen=True)
class StatedNumber:
    text: str
    value: Decimal
    decimals: int
    percent: bool


def extract_numbers(text: str) -> list[StatedNumber]:
    """Every number written in a text, in any of the digit systems NOVA replies in.

    Signs are ignored on purpose: "a fall of 12%" and "-12%" state the same
    figure, and tool results carry reversals as positive amounts.
    """
    found: list[StatedNumber] = []
    for match in _NUMBER.finditer(text.translate(_DIGITS)):
        token = match.group(0)
        digits = token.rstrip("%").replace(",", "")
        try:
            value = Decimal(digits)
        except InvalidOperation:  # pragma: no cover - the pattern only matches digits
            continue
        decimals = len(digits.split(".", 1)[1]) if "." in digits else 0
        found.append(
            StatedNumber(text=token, value=value, decimals=decimals, percent=token.endswith("%"))
        )
    return found


def grounded_values_in(text: str) -> set[Decimal]:
    """The numbers a tool result (or NOVA's own instructions) put on the table."""
    return {number.value for number in extract_numbers(text)}


def grounded_values_in_result(result: object) -> set[Decimal]:
    """The figures one tool result put on the table, ids aside.

    UUIDs are removed first: their hex fragments are not figures, and would let
    a reply "ground" a number by luck. Used for this turn's tool calls and for
    the ones conversation memory brings back.
    """
    text = UUID_PATTERN.sub("", json.dumps(result, default=str, ensure_ascii=False))
    return grounded_values_in(text)


def _is_grounded(number: StatedNumber, grounded: set[Decimal]) -> bool:
    # A number written to N decimals matches anything that rounds to it.
    tolerance = Decimal(1).scaleb(-number.decimals) / 2
    for value in grounded:
        candidates = (value, value * 100) if number.percent else (value,)
        if any(abs(candidate - number.value) <= tolerance for candidate in candidates):
            return True
    return False


def find_ungrounded_numbers(text: str, grounded: set[Decimal]) -> list[str]:
    """Numbers in a reply that no tool returned this turn.

    Grounded means equal at the reply's own precision (48,250 matches 48250.00),
    or a ratio written as a percentage (0.1833 matches "18.3%").
    """
    return [
        number.text
        for number in extract_numbers(text)
        if not (
            not number.percent and number.decimals == 0 and number.value <= SMALL_INTEGER_EXEMPTION
        )
        and not _is_grounded(number, grounded)
    ]


# --- proposed actions (docs/13 section 8) -----------------------------------


class ProposedActionKind(StrEnum):
    ADJUST_WORKING_HOURS = "adjust_working_hours"
    ADD_SCHEDULE_EXCEPTION = "add_schedule_exception"
    CHANGE_QUEUE_HOURS = "change_queue_hours"
    UPDATE_LISTING = "update_listing"
    REVIEW_SERVICE_PRICE = "review_service_price"
    PROMOTE_SERVICE = "promote_service"
    REBALANCE_PROVIDER_WORKLOAD = "rebalance_provider_workload"
    START_RETENTION_CAMPAIGN = "start_retention_campaign"


class ProposalTarget(StrEnum):
    PROVIDER = "provider"
    SERVICE = "service"
    LOCATION = "location"
    BUSINESS = "business"


@dataclass(frozen=True)
class ProposalRule:
    target: ProposalTarget
    #: The endpoint a person uses to apply it. None where NOVA has none yet.
    apply_via: str | None


PROPOSAL_RULES: dict[ProposedActionKind, ProposalRule] = {
    ProposedActionKind.ADJUST_WORKING_HOURS: ProposalRule(
        ProposalTarget.PROVIDER,
        "PUT /api/v1/tenants/{tenant_id}/schedules/providers/{provider_id}",
    ),
    ProposedActionKind.ADD_SCHEDULE_EXCEPTION: ProposalRule(
        ProposalTarget.PROVIDER,
        "POST /api/v1/tenants/{tenant_id}/schedules/providers/{provider_id}/exceptions",
    ),
    ProposedActionKind.CHANGE_QUEUE_HOURS: ProposalRule(
        ProposalTarget.LOCATION, "PATCH /api/v1/tenants/{tenant_id}/queues/{queue_id}/open"
    ),
    ProposedActionKind.UPDATE_LISTING: ProposalRule(
        ProposalTarget.BUSINESS,
        "PATCH /api/v1/tenants/{tenant_id}/catalog/businesses/{business_id}/listing",
    ),
    ProposedActionKind.REVIEW_SERVICE_PRICE: ProposalRule(ProposalTarget.SERVICE, None),
    ProposedActionKind.PROMOTE_SERVICE: ProposalRule(ProposalTarget.SERVICE, None),
    ProposedActionKind.REBALANCE_PROVIDER_WORKLOAD: ProposalRule(
        ProposalTarget.PROVIDER,
        "POST /api/v1/tenants/{tenant_id}/bookings/{booking_id}/reschedule",
    ),
    ProposedActionKind.START_RETENTION_CAMPAIGN: ProposalRule(ProposalTarget.BUSINESS, None),
}

MAX_PROPOSALS_PER_TURN = 5


@dataclass(frozen=True)
class ProposedAction:
    """A recommendation, never an instruction. Nothing in NOVA executes it."""

    id: str
    kind: ProposedActionKind
    title: str
    rationale: str
    metric: str
    target: ProposalTarget
    target_id: UUID | None
    apply_via: str | None


def check_proposal(
    kind: str, *, metric: str, metrics_used: set[str], already_proposed: int
) -> tuple[ProposedActionKind, ProposalRule]:
    """Admits a proposal only of a known kind, citing a metric read this turn."""
    try:
        parsed = ProposedActionKind(kind)
    except ValueError:
        allowed = ", ".join(k.value for k in ProposedActionKind)
        raise GuardrailError(
            GuardrailViolation.PROPOSAL_REFUSED,
            f"'{kind}' is not an action NOVA can propose. Use one of: {allowed}.",
        ) from None
    if already_proposed >= MAX_PROPOSALS_PER_TURN:
        raise GuardrailError(
            GuardrailViolation.PROPOSAL_REFUSED,
            f"At most {MAX_PROPOSALS_PER_TURN} actions can be proposed in one reply.",
        )
    if metric not in metrics_used:
        raise GuardrailError(
            GuardrailViolation.PROPOSAL_REFUSED,
            f"A proposal must cite a metric read in this conversation; '{metric}' was not.",
        )
    return parsed, PROPOSAL_RULES[parsed]
