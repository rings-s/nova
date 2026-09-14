"""Pure domain tests for identity — no database.

The validators now live in `app.core.validators` (shared with catalog) and are
re-exported by `identity.domain`; importing them through the module keeps the
test honest about the module's public surface.
"""

import pytest

from app.core.exceptions import ValidationDomainError
from app.modules.identity.domain import (
    MembershipRole,
    StaffPermission,
    generate_slug,
    may_manage_role,
    require_bilingual_text,
    role_allows,
    validate_gcc_phone,
    validate_timezone,
)

ALLOWED_CODES = ["966", "971"]


def test_validate_gcc_phone_accepts_valid_number() -> None:
    assert validate_gcc_phone("+966500000000", ALLOWED_CODES) == "+966500000000"


def test_validate_gcc_phone_rejects_unsupported_country_code() -> None:
    with pytest.raises(ValidationDomainError):
        validate_gcc_phone("+15550000000", ALLOWED_CODES)


def test_validate_gcc_phone_rejects_non_e164_format() -> None:
    with pytest.raises(ValidationDomainError):
        validate_gcc_phone("0500000000", ALLOWED_CODES)


def test_validate_timezone_accepts_known_zone() -> None:
    assert validate_timezone("Asia/Riyadh") == "Asia/Riyadh"


def test_validate_timezone_rejects_unknown_zone() -> None:
    with pytest.raises(ValidationDomainError):
        validate_timezone("Mars/Olympus_Mons")


def test_require_bilingual_text_requires_both_languages() -> None:
    require_bilingual_text("Salon", "صالون")

    with pytest.raises(ValidationDomainError):
        require_bilingual_text("Salon", "   ")

    with pytest.raises(ValidationDomainError):
        require_bilingual_text("", "صالون")


def test_generate_slug_normalises_text() -> None:
    assert generate_slug("  Glow & Go Salon!! ") == "glow-go-salon"


def test_generate_slug_rejects_text_with_no_slug_characters() -> None:
    with pytest.raises(ValidationDomainError):
        generate_slug("!!!")


class TestMayManageRole:
    """The per-tenant authority matrix.

    Pure, so the whole rule is testable without a database — which matters
    because the thing it guards is "who can hand out access to a business".
    """

    def test_an_owner_may_grant_any_role_including_another_owner(self) -> None:
        for target in MembershipRole:
            assert may_manage_role(MembershipRole.OWNER, target)

    def test_a_manager_may_appoint_staff_but_not_a_peer_or_an_owner(self) -> None:
        assert may_manage_role(MembershipRole.MANAGER, MembershipRole.RECEPTIONIST)
        assert may_manage_role(MembershipRole.MANAGER, MembershipRole.PROVIDER)

        # Otherwise "manager" is just "owner" with one extra step: promote a
        # second manager, have them promote you.
        assert not may_manage_role(MembershipRole.MANAGER, MembershipRole.MANAGER)
        assert not may_manage_role(MembershipRole.MANAGER, MembershipRole.OWNER)

    def test_receptionists_and_providers_manage_nobody(self) -> None:
        for actor in (MembershipRole.RECEPTIONIST, MembershipRole.PROVIDER):
            for target in MembershipRole:
                assert not may_manage_role(actor, target)

    def test_a_non_member_manages_nobody(self) -> None:
        """The case that carries the weight now that customers reach every tenant.

        `None` is what both a customer principal and a staff member of a
        *different* salon look like when their role is read for this tenant.
        """
        for target in MembershipRole:
            assert not may_manage_role(None, target)

    def test_a_service_principal_bypasses_the_matrix(self) -> None:
        """Platform machinery has no membership row to read a role from."""
        for target in MembershipRole:
            assert may_manage_role(None, target, actor_is_service=True)

    def test_role_values_are_the_strings_stored_in_the_column(self) -> None:
        """`memberships.role` is a plain String(32), so no ORM enum coercion
        happens on load and the value read back is a bare `str`. Comparisons
        only keep working because these are StrEnum members."""
        assert MembershipRole.OWNER == "owner"
        assert MembershipRole("receptionist") is MembershipRole.RECEPTIONIST
        assert may_manage_role(MembershipRole("owner"), MembershipRole("manager"))


class TestRoleAllows:
    """Who may move money, commit the business to spend, or read what it earns.

    The policy is one table in the domain; these pin it, so changing who may
    refund a customer is a deliberate edit in two places rather than one.
    """

    def test_an_owner_holds_every_permission(self) -> None:
        for permission in StaffPermission:
            assert role_allows(MembershipRole.OWNER, permission)

    def test_a_manager_refunds_and_reads_the_numbers_but_does_not_decide_the_plan(self) -> None:
        assert role_allows(MembershipRole.MANAGER, StaffPermission.REFUND_PAYMENTS)
        assert role_allows(MembershipRole.MANAGER, StaffPermission.VIEW_FINANCIALS)
        assert role_allows(MembershipRole.MANAGER, StaffPermission.VIEW_ANALYTICS)
        assert not role_allows(MembershipRole.MANAGER, StaffPermission.MANAGE_SUBSCRIPTION)

    def test_receptionists_and_providers_hold_none(self) -> None:
        for role in (MembershipRole.RECEPTIONIST, MembershipRole.PROVIDER):
            for permission in StaffPermission:
                assert not role_allows(role, permission)

    def test_a_non_member_holds_none_and_a_service_principal_holds_all(self) -> None:
        for permission in StaffPermission:
            assert not role_allows(None, permission)
            assert role_allows(None, permission, actor_is_service=True)
