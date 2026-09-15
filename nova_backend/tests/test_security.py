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
from fastapi import Request

from app.core.config import Settings, get_settings
from app.core.security import (
    REFRESH_TOKEN_TTL_SECONDS,
    AuthenticationError,
    AuthorizationError,
    Principal,
    PrincipalKind,
    TokenState,
    _dev_bypass_principal,
    _principal_from_claims,
    _service_kind_refusal,
    decode_purpose_token,
    decode_token,
    get_principal,
    issue_purpose_token,
    issue_token,
    purpose_key,
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
        "iat": time.time(),
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

    def test_rejects_token_without_an_issue_time(self):
        claims = valid_claims()
        del claims["iat"]
        with pytest.raises(AuthenticationError):
            decode_token(make_token(claims), secret=SECRET)

    @pytest.mark.parametrize("issued_at", ["0", [0], {"at": 0}, True, float("inf"), float("nan")])
    def test_rejects_an_issue_time_that_is_not_a_finite_number(self, issued_at):
        with pytest.raises(AuthenticationError):
            decode_token(make_token(valid_claims(iat=issued_at)), secret=SECRET)

    def test_rejects_a_lifetime_longer_than_the_refresh_ttl(self):
        """However far out a forger sets `exp`, this app never mints a token
        longer-lived than a refresh token — so this bounds even a token forged
        with a leaked SECRET_KEY (TM-03)."""
        now = time.time()
        claims = valid_claims(iat=now, exp=now + REFRESH_TOKEN_TTL_SECONDS + 1)
        with pytest.raises(AuthenticationError):
            decode_token(make_token(claims), secret=SECRET)

    def test_accepts_a_lifetime_exactly_at_the_refresh_ttl(self):
        """The boundary a real refresh token sits on must not be refused."""
        now = time.time()
        claims = valid_claims(iat=now, exp=now + REFRESH_TOKEN_TTL_SECONDS)
        assert decode_token(make_token(claims), secret=SECRET)["sub"] == claims["sub"]

    def test_rejects_malformed_token(self):
        for bad in ("", "not-a-token", "a.b", "a.b.c.d"):
            with pytest.raises(AuthenticationError):
                decode_token(bad, secret=SECRET)

    @pytest.mark.parametrize("header", ["[]", '["HS256"]', '"HS256"', "1", "null", "[" * 100_000])
    def test_a_header_that_is_not_an_object_is_refused_not_crashed_on(self, header):
        """Read as a dict, a JSON array raised AttributeError: a 500 for any anonymous caller."""
        payload = _b64(json.dumps(valid_claims()).encode())
        with pytest.raises(AuthenticationError):
            decode_token(f"{_b64(header.encode())}.{payload}.{_b64(b'sig')}", secret=SECRET)

    @pytest.mark.parametrize("claims", ["[]", "1", '"claims"', "null"])
    def test_signed_claims_that_are_not_an_object_are_refused(self, claims):
        header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        payload = _b64(claims.encode())
        signature = hmac.new(SECRET.encode(), f"{header}.{payload}".encode(), sha256).digest()
        with pytest.raises(AuthenticationError):
            decode_token(f"{header}.{payload}.{_b64(signature)}", secret=SECRET)

    @pytest.mark.parametrize(
        "exp", ["9999999999", [9999999999], {"at": 9999999999}, True, float("inf"), float("nan")]
    )
    def test_an_expiry_that_is_not_a_finite_number_is_refused(self, exp):
        """NaN compares false with everything, so a token expiring at NaN never expired."""
        with pytest.raises(AuthenticationError):
            decode_token(make_token(valid_claims(exp=exp)), secret=SECRET)

    @pytest.mark.parametrize(
        "claims",
        [
            {"sub": 12345},
            {"sub": str(uuid4()), "tenants": 7},
            {"sub": str(uuid4()), "roles": [["owner"]]},
            {"sub": str(uuid4()), "kind": ["staff"]},
        ],
    )
    def test_claims_of_the_wrong_shape_are_refused(self, claims):
        with pytest.raises(AuthenticationError):
            _principal_from_claims(claims)


class TestPurposeTokens:
    """`issue_purpose_token` / `decode_purpose_token` — a narrower JWT for
    proving one specific fact about an account (docs/14 TM-01), not the full
    `Principal` shape `issue_token` mints. Used directly by
    `AuthService.request_phone_verification` / `confirm_phone_verification`.
    """

    def test_a_token_round_trips_for_its_own_purpose(self):
        subject = uuid4()
        token = issue_purpose_token(
            subject_id=subject, purpose="phone_verification", secret=SECRET, ttl_seconds=600
        )

        claims = decode_purpose_token(token, purpose="phone_verification", secret=SECRET)

        assert claims["sub"] == str(subject)
        assert claims["typ"] == "phone_verification"
        assert "jti" in claims

    def test_a_token_carries_nothing_but_sub_typ_jti_and_time(self):
        """No PII, no business data — whatever channel this travels over
        (WhatsApp) is a front channel in the Curity JWT best-practices sense:
        readable by the provider, visible in a lock-screen preview, sitting
        in chat history."""
        token = issue_purpose_token(
            subject_id=uuid4(), purpose="phone_verification", secret=SECRET, ttl_seconds=600
        )
        claims = decode_purpose_token(token, purpose="phone_verification", secret=SECRET)

        assert set(claims) == {"sub", "typ", "jti", "iat", "exp"}

    def test_a_token_does_not_verify_for_a_different_purpose(self):
        token = issue_purpose_token(
            subject_id=uuid4(), purpose="phone_verification", secret=SECRET, ttl_seconds=600
        )

        with pytest.raises(AuthenticationError):
            decode_purpose_token(token, purpose="something_else", secret=SECRET)

    def test_a_purpose_token_does_not_verify_as_another_purposes_token_even_by_signature(self):
        """`purpose_key` derives a different signing key per purpose, so this
        fails at signature verification, before the `typ` claim is even
        compared — a stronger separation than a shared key with a claim
        check alone would give."""
        token = issue_purpose_token(
            subject_id=uuid4(), purpose="phone_verification", secret=SECRET, ttl_seconds=600
        )
        wrong_key = purpose_key(SECRET, "something_else")

        with pytest.raises(AuthenticationError):
            decode_token(token, secret=wrong_key)

    def test_a_plain_access_token_does_not_verify_as_a_purpose_token(self):
        """The root secret and a purpose-derived key never coincide."""
        access_token = issue_token(subject_id=uuid4(), kind=PrincipalKind.CUSTOMER, secret=SECRET)

        with pytest.raises(AuthenticationError):
            decode_purpose_token(access_token, purpose="phone_verification", secret=SECRET)

    async def test_a_non_access_typ_cannot_authenticate_a_request(self):
        """Belt and suspenders: even setting `purpose_key` derivation aside,
        `get_principal` only ever accepts `typ="access"` — a token signed
        with the plain root secret and `typ="phone_verification"` would
        still be refused as a bearer token, the same way a refresh token is."""
        token = make_token(valid_claims(typ="phone_verification"), secret=get_settings().secret_key)

        with pytest.raises(AuthenticationError):
            await get_principal(_request(token), token_state=_accounts(None))

    def test_an_expired_purpose_token_is_refused(self):
        token = issue_purpose_token(
            subject_id=uuid4(), purpose="phone_verification", secret=SECRET, ttl_seconds=-1
        )

        with pytest.raises(AuthenticationError):
            decode_purpose_token(token, purpose="phone_verification", secret=SECRET)

    def test_different_purposes_derive_different_keys(self):
        assert purpose_key(SECRET, "phone_verification") != purpose_key(SECRET, "invite")
        assert purpose_key(SECRET, "phone_verification") != SECRET


def _request(token: str) -> Request:
    return Request({"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())]})


def _token(subject_id, *, kind: PrincipalKind = PrincipalKind.STAFF, version: int = 0) -> str:
    return issue_token(
        subject_id=subject_id, kind=kind, secret=get_settings().secret_key, token_version=version
    )


def _accounts(state: TokenState | None):
    async def lookup(subject_id):
        return state

    return lookup


class TestRequestAuthentication:
    """`get_principal` on the real token path, with the account read supplied."""

    async def test_a_malformed_token_is_a_401_not_a_500(self):
        payload = _b64(json.dumps(valid_claims()).encode())
        with pytest.raises(AuthenticationError):
            await get_principal(_request(f"{_b64(b'[]')}.{payload}.x"), token_state=_accounts(None))

    async def test_a_token_matching_its_account_authenticates(self):
        subject = uuid4()
        principal = await get_principal(
            _request(_token(subject, version=3)),
            token_state=_accounts(TokenState(token_version=3, is_active=True)),
        )
        assert principal.subject_id == subject

    async def test_a_token_issued_before_its_account_was_revoked_is_refused(self):
        """Logout-everywhere or a revoked membership bumped the version: refused now."""
        with pytest.raises(AuthenticationError):
            await get_principal(
                _request(_token(uuid4(), version=2)),
                token_state=_accounts(TokenState(token_version=3, is_active=True)),
            )

    async def test_a_deactivated_account_is_refused(self):
        with pytest.raises(AuthenticationError):
            await get_principal(
                _request(_token(uuid4(), kind=PrincipalKind.CUSTOMER)),
                token_state=_accounts(TokenState(token_version=0, is_active=False)),
            )

    async def test_a_token_whose_account_is_gone_is_refused(self):
        with pytest.raises(AuthenticationError):
            await get_principal(_request(_token(uuid4())), token_state=_accounts(None))

    async def test_a_service_token_has_no_account_to_check(self):
        async def no_lookup(subject_id):
            raise AssertionError("a service principal has no account row")

        principal = await get_principal(
            _request(_token(uuid4(), kind=PrincipalKind.SERVICE)), token_state=no_lookup
        )
        assert principal.kind is PrincipalKind.SERVICE

    async def test_a_service_token_is_refused_outside_local_and_test(self, monkeypatch):
        """Only local/test honour it — see TestServiceKindRefusal and TM-03."""
        import app.core.security as security_module

        deployed = get_settings().model_copy(update={"env": "production"})
        monkeypatch.setattr(security_module, "get_settings", lambda: deployed)

        async def no_lookup(subject_id):
            raise AssertionError("a refused service principal never reaches the account check")

        with pytest.raises(AuthenticationError):
            await get_principal(
                _request(_token(uuid4(), kind=PrincipalKind.SERVICE)), token_state=no_lookup
            )


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


class TestServiceKindRefusal:
    """A bearer token naming `kind=service` proves only that its holder has
    `SECRET_KEY` — the app itself never puts that claim on a token. Honoured
    in the same environments the dev bypass is (TM-03)."""

    @pytest.mark.parametrize("env", ["local", "test"])
    def test_allowed_in_development(self, env):
        assert _service_kind_refusal(env) is None

    @pytest.mark.parametrize("env", ["staging", "production"])
    def test_refused_when_deployed(self, env):
        assert _service_kind_refusal(env) is not None
