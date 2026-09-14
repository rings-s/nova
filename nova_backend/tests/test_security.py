"""Tests for authentication and tenant authorization.

Pure — no database. These cover the token path itself, which the API tests
deliberately stub out.
"""

import base64
import hmac
import json
import time
from hashlib import sha256
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.security import (
    AuthenticationError,
    AuthorizationError,
    Principal,
    PrincipalKind,
    _dev_bypass_principal,
    decode_token,
    require_tenant_access,
)

SECRET = "test-secret"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def make_token(claims: dict, *, secret: str = SECRET, alg: str = "HS256") -> str:
    header = _b64(json.dumps({"alg": alg, "typ": "JWT"}).encode())
    payload = _b64(json.dumps(claims).encode())
    signature = hmac.new(secret.encode(), f"{header}.{payload}".encode(), sha256).digest()
    return f"{header}.{payload}.{_b64(signature)}"


def valid_claims(**overrides) -> dict:
    claims = {
        "sub": str(uuid4()),
        "kind": "customer",
        "tenants": [],
        "exp": time.time() + 3600,
    }
    claims.update(overrides)
    return claims


class TestTokenVerification:
    def test_accepts_a_correctly_signed_token(self):
        claims = valid_claims()
        assert decode_token(make_token(claims), secret=SECRET)["sub"] == claims["sub"]

    def test_rejects_a_token_signed_with_the_wrong_secret(self):
        token = make_token(valid_claims(), secret="attacker-secret")
        with pytest.raises(AuthenticationError):
            decode_token(token, secret=SECRET)

    def test_rejects_a_tampered_payload(self):
        header, _payload, signature = make_token(valid_claims()).split(".")
        forged_payload = _b64(json.dumps(valid_claims(kind="staff")).encode())
        with pytest.raises(AuthenticationError):
            decode_token(f"{header}.{forged_payload}.{signature}", secret=SECRET)

    def test_rejects_alg_none_forgery(self):
        """The classic JWT bypass: unsigned token claiming no algorithm."""
        header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        payload = _b64(json.dumps(valid_claims(kind="staff")).encode())
        with pytest.raises(AuthenticationError):
            decode_token(f"{header}.{payload}.", secret=SECRET)

    def test_rejects_expired_token(self):
        with pytest.raises(AuthenticationError):
            decode_token(make_token(valid_claims(exp=time.time() - 1)), secret=SECRET)

    def test_rejects_token_without_expiry(self):
        claims = valid_claims()
        del claims["exp"]
        with pytest.raises(AuthenticationError):
            decode_token(make_token(claims), secret=SECRET)

    def test_rejects_malformed_token(self):
        for bad in ("", "not-a-token", "a.b", "a.b.c.d"):
            with pytest.raises(AuthenticationError):
                decode_token(bad, secret=SECRET)


class TestTenantAuthorization:
    async def test_allows_a_member_of_the_tenant(self):
        tenant_id = uuid4()
        principal = Principal(
            subject_id=uuid4(),
            kind=PrincipalKind.STAFF,
            tenant_ids=frozenset({tenant_id}),
        )
        assert await require_tenant_access(tenant_id, principal) == tenant_id

    async def test_denies_access_to_another_tenant(self):
        """The defect this whole layer exists to close."""
        principal = Principal(
            subject_id=uuid4(),
            kind=PrincipalKind.STAFF,
            tenant_ids=frozenset({uuid4()}),
        )
        with pytest.raises(AuthorizationError):
            await require_tenant_access(uuid4(), principal)

    async def test_denies_staff_with_no_tenants(self):
        """Staff authority still comes from membership and nothing else."""
        principal = Principal(subject_id=uuid4(), kind=PrincipalKind.STAFF)
        with pytest.raises(AuthorizationError):
            await require_tenant_access(uuid4(), principal)

    async def test_service_principal_is_not_tenant_scoped(self):
        principal = Principal(subject_id=uuid4(), kind=PrincipalKind.SERVICE)
        tenant_id = uuid4()
        assert await require_tenant_access(tenant_id, principal) == tenant_id


class TestCustomerTenantAccess:
    """A customer may reach any salon — and that is not the same as authority.

    This inverts an earlier rule that denied every customer principal. The old
    behaviour was a contradiction rather than a policy: `_issue_pair` assigns
    kind=CUSTOMER exactly when a user has no memberships, so a customer was
    refused by every tenant-scoped route and self-service booking could not
    happen at all.

    What replaces it is not "customers may do anything in any tenant" — it is
    `require_staff` on operational routes plus per-row ownership checks
    everywhere else. These tests pin the first half; the ownership half is
    exercised against a database.
    """

    async def test_a_customer_may_reach_a_salon_they_have_never_visited(self):
        principal = Principal(subject_id=uuid4(), kind=PrincipalKind.CUSTOMER)
        tenant_id = uuid4()
        assert await require_tenant_access(tenant_id, principal) == tenant_id

    async def test_a_customer_is_still_not_staff(self):
        """The line that keeps the previous test from being a hole."""
        principal = Principal(subject_id=uuid4(), kind=PrincipalKind.CUSTOMER)
        assert not principal.is_staff

    async def test_require_staff_refuses_a_customer(self):
        from app.core.security import require_staff

        principal = Principal(subject_id=uuid4(), kind=PrincipalKind.CUSTOMER)
        with pytest.raises(AuthorizationError):
            await require_staff(principal)

    async def test_tenant_memberships_are_irrelevant_to_a_customer(self):
        """Reaching a tenant no longer depends on `tenant_ids` for customers,
        so a stale or empty claim must not change the answer."""
        subject = uuid4()
        target = uuid4()
        for tenants in (frozenset(), frozenset({uuid4()}), frozenset({target})):
            principal = Principal(
                subject_id=subject, kind=PrincipalKind.CUSTOMER, tenant_ids=tenants
            )
            assert await require_tenant_access(target, principal) == target


class TestBookingCustomerResolution:
    """Guards the 'book as anyone' hole in the booking endpoints."""

    def test_customer_books_for_themselves(self):
        from app.modules.booking.dependencies import resolve_booking_customer

        principal = Principal(subject_id=uuid4(), kind=PrincipalKind.CUSTOMER)
        assert resolve_booking_customer(None, principal) == principal.subject_id

    def test_customer_cannot_book_for_someone_else(self):
        from app.modules.booking.dependencies import resolve_booking_customer

        principal = Principal(subject_id=uuid4(), kind=PrincipalKind.CUSTOMER)
        with pytest.raises(AuthorizationError):
            resolve_booking_customer(uuid4(), principal)

    def test_staff_may_book_on_behalf_of_a_customer(self):
        from app.modules.booking.dependencies import resolve_booking_customer

        principal = Principal(subject_id=uuid4(), kind=PrincipalKind.STAFF)
        customer_id = uuid4()
        assert resolve_booking_customer(customer_id, principal) == customer_id


class TestDevBypass:
    """The request-time re-check, for settings built without validation.

    `Settings` refuses these states at startup (tests/test_config.py), but
    `model_construct` skips validation, which is the gap this check covers.
    """

    @staticmethod
    def _settings(**fields: object) -> Settings:
        values: dict[str, object] = {
            "auth_dev_bypass": True,
            "env": "local",
            "cloudflare_tunnel_token": None,
        }
        values.update(fields)
        return Settings.model_construct(**values)

    def test_serves_a_service_principal_on_a_developer_machine(self):
        principal = _dev_bypass_principal(self._settings())
        assert principal is not None and principal.kind is PrincipalKind.SERVICE

    def test_off_means_no_principal(self):
        assert _dev_bypass_principal(self._settings(auth_dev_bypass=False)) is None

    def test_refuses_when_deployed(self):
        with pytest.raises(AuthenticationError):
            _dev_bypass_principal(self._settings(env="production"))

    def test_refuses_on_a_stack_a_tunnel_publishes(self):
        with pytest.raises(AuthenticationError):
            _dev_bypass_principal(self._settings(cloudflare_tunnel_token="token"))
