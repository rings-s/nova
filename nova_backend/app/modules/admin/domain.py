"""admin · DOMAIN layer — what the platform console may show and do.

Pure: no FastAPI, no SQLAlchemy. The repository hands this layer plain Python
values and column names; the rules about which of them a superuser may see, and
which curated actions exist, live here so they can be tested without a database.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum, StrEnum
from typing import Any
from uuid import UUID

#: What a masked value reads as. Never the value's length or a prefix of it.
MASK = "••••••"

#: Column names whose value is a credential or a derivative of one: a hash
#: still identifies a token, and a hold token or fingerprint can be replayed.
_SECRET_FRAGMENTS = ("password", "secret", "token", "fingerprint")

#: Column names shown with all but their last four characters masked. The
#: gateway's own references: enough to find the record in Moyasar's dashboard,
#: not enough to be someone else's handle on it.
_PARTIAL_PREFIXES = ("gateway_", "provider_message_id", "external_event_id")

#: JSON keys scrubbed anywhere in a JSONB value (webhook payloads, idempotency
#: replays, notification payloads), for the same reason as the columns above.
#: `qr` covers a ticket's QR payload, which is itself the credential.
_SECRET_JSON_FRAGMENTS = (*_SECRET_FRAGMENTS, "qr", "hash", "authorization", "api_key")


def is_secret_column(name: str) -> bool:
    lowered = name.lower()
    return any(fragment in lowered for fragment in _SECRET_FRAGMENTS)


def is_partial_column(name: str) -> bool:
    return name.lower().startswith(_PARTIAL_PREFIXES)


def is_masked_column(name: str) -> bool:
    """Whether a superuser sees less than the stored value. Masked columns are
    neither searched nor filtered on, or a search would leak them one guess at
    a time."""
    return is_secret_column(name) or is_partial_column(name)


def _partial(value: str) -> str:
    return MASK if len(value) <= 8 else f"{MASK}{value[-4:]}"


def scrub_json(value: Any) -> Any:
    """A copy of a JSON value with every secret-looking key's value masked."""
    if isinstance(value, dict):
        return {
            key: (
                MASK
                if any(fragment in str(key).lower() for fragment in _SECRET_JSON_FRAGMENTS)
                else scrub_json(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub_json(item) for item in value]
    return value


def display_value(column: str, value: Any) -> Any:
    """A stored value as the console shows it: JSON-safe, and masked where the
    column calls for it. `None` stays `None`, so "not set" is still visible."""
    if value is None:
        return None
    if is_secret_column(column):
        return MASK
    if is_partial_column(column):
        return _partial(str(value))
    return _jsonable(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID | Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict | list):
        return scrub_json(_jsonable_tree(value))
    if isinstance(value, tuple | set | frozenset):
        return [_jsonable(item) for item in value]
    return str(value)


def _jsonable_tree(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable_tree(item) for item in value]
    return _jsonable(value)


# --- row identity ------------------------------------------------------------

#: Joins a composite primary key into one path segment (`provider_services`).
ROW_ID_SEPARATOR = "~"


def encode_row_id(values: list[Any]) -> str:
    return ROW_ID_SEPARATOR.join(str(value) for value in values)


def decode_row_id(row_id: str, key_length: int) -> list[str] | None:
    parts = row_id.split(ROW_ID_SEPARATOR)
    return parts if len(parts) == key_length and all(parts) else None


# --- grouping ----------------------------------------------------------------

#: Which module owns each table, for the console's sidebar. A table missing
#: here is listed under "platform" rather than hidden.
TABLE_GROUPS: dict[str, str] = {
    "tenants": "identity",
    "users": "identity",
    "memberships": "identity",
    "membership_invites": "identity",
    "customers": "identity",
    "businesses": "catalog",
    "business_photos": "catalog",
    "locations": "catalog",
    "services": "catalog",
    "service_categories": "catalog",
    "providers": "catalog",
    "provider_services": "catalog",
    "marketplace_referrals": "discovery",
    "bookings": "booking",
    "provider_schedules": "booking",
    "schedule_exceptions": "booking",
    "slot_holds": "booking",
    "queues": "queue",
    "queue_entries": "queue",
    "tickets": "queue",
    "reviews": "review",
    "payments": "payment",
    "payment_refunds": "payment",
    "webhook_events": "payment",
    "subscriptions": "billing",
    "subscription_checkouts": "billing",
    "invoices": "billing",
    "commission_lines": "billing",
    "payouts": "billing",
    "customer_business_first_bookings": "billing",
    "notifications": "notification",
    "domain_events": "platform",
    "idempotency_keys": "platform",
    "admin_audit_log": "platform",
}


def group_of(table: str) -> str:
    return TABLE_GROUPS.get(table, "platform")


# --- audit -------------------------------------------------------------------


class AdminAuditKind(StrEnum):
    """What a superuser did. Every read of tenant data is recorded, not only
    writes: the console's reach across tenants is the thing worth auditing."""

    LIST = "list"
    VIEW = "view"
    ACTION = "action"


# --- curated actions ---------------------------------------------------------


class AdminAction(StrEnum):
    """The only writes the console can make. Each runs through the owning
    module's service, so state machines, events and policies still apply; there
    is no generic "edit this row"."""

    DEACTIVATE_USER = "deactivate_user"
    REACTIVATE_USER = "reactivate_user"
    REVOKE_SESSIONS = "revoke_sessions"
    HIDE_LISTING = "hide_listing"
    SHOW_LISTING = "show_listing"
    CANCEL_BOOKING = "cancel_booking"


@dataclass(frozen=True, slots=True)
class ActionSpec:
    action: AdminAction
    table: str
    label: str
    #: Asks for a confirmation in the console before running.
    destructive: bool = False
    #: A free-text reason the console must collect (and the audit log keeps).
    requires_reason: bool = False


ACTIONS: tuple[ActionSpec, ...] = (
    ActionSpec(AdminAction.DEACTIVATE_USER, "users", "Deactivate account", destructive=True),
    ActionSpec(AdminAction.REACTIVATE_USER, "users", "Reactivate account"),
    ActionSpec(AdminAction.REVOKE_SESSIONS, "users", "Sign out everywhere", destructive=True),
    ActionSpec(AdminAction.HIDE_LISTING, "businesses", "Hide from marketplace", destructive=True),
    ActionSpec(AdminAction.SHOW_LISTING, "businesses", "Show on marketplace"),
    ActionSpec(
        AdminAction.CANCEL_BOOKING,
        "bookings",
        "Cancel booking",
        destructive=True,
        requires_reason=True,
    ),
)


def actions_for(table: str) -> list[ActionSpec]:
    return [spec for spec in ACTIONS if spec.table == table]


def action_spec(table: str, action: str) -> ActionSpec | None:
    return next(
        (spec for spec in ACTIONS if spec.table == table and spec.action.value == action), None
    )


#: The longest reason kept. Long enough for a sentence or two.
MAX_REASON_LENGTH = 500


def clean_reason(spec: ActionSpec, reason: str | None) -> str | None:
    """The reason as it will be stored, or a message saying why it is refused."""
    reason = (reason or "").strip() or None
    if spec.requires_reason and reason is None:
        raise ValueError("This action needs a reason.")
    if reason is not None and len(reason) > MAX_REASON_LENGTH:
        raise ValueError(f"Keep the reason under {MAX_REASON_LENGTH} characters.")
    return reason
