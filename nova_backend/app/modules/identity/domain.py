"""Domain rules for the identity module.

Per the architecture decision recorded in docs 06, `identity` is a module whose
invariants are field-level validation rather than a state machine, so it keeps
the pure-function style rather than a separate rich entity — the ORM `Tenant`
is the domain object. Modules with real lifecycles (booking, queue, payment)
define entity classes here instead.

The generic validators live in `app.core.validators` because `catalog` needs
the same rules.
"""

from enum import StrEnum

from app.core.validators import (
    generate_slug,
    require_bilingual_text,
    validate_gcc_phone,
    validate_timezone,
)


class MembershipRole(StrEnum):
    """What a user may do inside one tenant.

    Domain vocabulary, so it lives here rather than in `models.py` — schemas,
    the router, and the pure rule below all need it, and importing it from the
    ORM module would drag SQLAlchemy into every one of them.
    """

    OWNER = "owner"
    MANAGER = "manager"
    RECEPTIONIST = "receptionist"
    PROVIDER = "provider"


#: Who may hand out which role. Roles a rank cannot grant are simply absent,
#: so the rule reads as "what this role can do" rather than a list of denials.
_ROLE_GRANTS: dict[MembershipRole, frozenset[MembershipRole]] = {
    MembershipRole.OWNER: frozenset(MembershipRole),
    # A manager runs the salon day to day but cannot appoint a peer or an
    # owner — otherwise "manager" is just "owner" with one extra step.
    MembershipRole.MANAGER: frozenset({MembershipRole.RECEPTIONIST, MembershipRole.PROVIDER}),
    MembershipRole.RECEPTIONIST: frozenset(),
    MembershipRole.PROVIDER: frozenset(),
}


def may_manage_role(
    actor: MembershipRole | None,
    target: MembershipRole,
    *,
    actor_is_service: bool = False,
) -> bool:
    """Whether `actor` may grant, change, or revoke a membership at `target`.

    `actor` is None when the caller holds no active membership in this tenant.
    That is the important case: a customer principal now reaches every tenant,
    and a staff member of one salon reaches their own — neither may administer
    a salon they are not part of, and None is what both look like here.

    Deliberately *not* driven by `Principal.roles`: that claim is minted from
    every active membership a user holds across all tenants, flattened into one
    set with no tenant key. Someone who owns salon A and answers the phone at
    salon B carries {"owner", "receptionist"} everywhere, so a role check
    against the token would let them administer salon B. The caller's role has
    to be read for the tenant in hand.
    """
    if actor_is_service:
        return True
    if actor is None:
        return False
    return target in _ROLE_GRANTS[actor]


class StaffPermission(StrEnum):
    """What a role unlocks beyond a staff member's day-to-day work.

    Ordinary operations — the calendar, the queue, check-in — stay open to every
    member of the salon (`require_staff`). These are the actions that move
    money, commit the business to spend, or read what it earns.
    """

    #: Subscribe, change plan, cancel: what the business pays NOVA.
    MANAGE_SUBSCRIPTION = "manage_subscription"
    #: Money leaving the business, back to a customer.
    REFUND_PAYMENTS = "refund_payments"
    #: Invoices, commission lines, payouts, the subscription's terms, the
    #: financial summary, and the accountant agent.
    VIEW_FINANCIALS = "view_financials"
    #: The analytics dashboards, revenue by provider among them, and the analyst
    #: and business manager agents.
    VIEW_ANALYTICS = "view_analytics"


#: Which role holds which permission, in one table so a salon's policy can be
#: read, and changed, in one place.
_ROLE_PERMISSIONS: dict[MembershipRole, frozenset[StaffPermission]] = {
    MembershipRole.OWNER: frozenset(StaffPermission),
    # Runs the salon day to day: refunds a customer and reads the numbers, but
    # does not decide what the business pays NOVA.
    MembershipRole.MANAGER: frozenset(
        {
            StaffPermission.REFUND_PAYMENTS,
            StaffPermission.VIEW_FINANCIALS,
            StaffPermission.VIEW_ANALYTICS,
        }
    ),
    # The front desk and the chair: the calendar and the queue, and nothing that
    # moves or reveals money. A stylist has no business reading a colleague's
    # takings.
    MembershipRole.RECEPTIONIST: frozenset(),
    MembershipRole.PROVIDER: frozenset(),
}


def role_allows(
    role: MembershipRole | None,
    permission: StaffPermission,
    *,
    actor_is_service: bool = False,
) -> bool:
    """Whether a caller holding `role` in this tenant may do what `permission` names.

    `role` is None for a caller with no active membership here, and None allows
    nothing. Like `may_manage_role`, this is never decided from
    `Principal.roles`, which is flattened across every tenant a user belongs to.
    """
    if actor_is_service:
        return True
    return role is not None and permission in _ROLE_PERMISSIONS[role]


__all__ = [
    "MembershipRole",
    "StaffPermission",
    "generate_slug",
    "may_manage_role",
    "require_bilingual_text",
    "role_allows",
    "validate_gcc_phone",
    "validate_timezone",
]
