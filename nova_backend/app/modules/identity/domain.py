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


__all__ = [
    "MembershipRole",
    "generate_slug",
    "may_manage_role",
    "require_bilingual_text",
    "validate_gcc_phone",
    "validate_timezone",
]
