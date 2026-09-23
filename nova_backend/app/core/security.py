"""Authentication and tenant authorization.

Before this module existed the API had NO authentication of any kind. Every
endpoint was reachable by anyone who could guess a UUID, which made the
tenant-scoping in `TenantScopedRepository` decorative: it stopped a caller
reading another tenant's row through the *wrong path*, but nothing stopped them
simply requesting the right one. ADR-0003 secured the plumbing; this secures
the door.

Design notes:

  - Tokens are HMAC-SHA256 JWTs verified with `settings.secret_key`. Implemented
    on the stdlib rather than adding a dependency, and deliberately verify-only
    — NOVA does not mint production tokens here.
  - Verification is constant-time (`hmac.compare_digest`) to avoid leaking the
    signature through timing.
  - `alg` is pinned to HS256. Accepting the token's own `alg` header is the
    classic JWT forgery ("alg: none") and is rejected explicitly.
  - It fails CLOSED. A missing, malformed or invalid token is 401 in every
    environment. The only bypass is an explicit local-development flag, and it
    refuses to engage outside `local`/`test` or on a stack a Cloudflare tunnel
    publishes.
  - Revocation is immediate. Each request re-reads the account's
    `token_version` and `is_active`, so logout-everywhere, a revoked membership
    or a deactivated account ends access at once, not when the token expires.
  - A token's lifetime is bounded even if `SECRET_KEY` leaks: `exp - iat` may
    not exceed the refresh-token TTL, so a forged token cannot claim an
    expiry further out than the longest one this app ever mints.
  - `kind=service` is the one claim that skips the revocation check above — it
    names no account to re-read. The app itself never issues one over HTTP
    (only the dev bypass builds a SERVICE principal, and only without a token
    at all), so a bearer token naming it is refused outside local/test: see
    docs/14 TM-03.
"""

import base64
import hmac
import json
import math
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from fastapi import Depends, Path, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DEVELOPMENT_ENVS, Settings, dev_bypass_refusal, get_settings
from app.core.exceptions import DomainError
from app.db.session import get_session_factory


class AuthenticationError(DomainError):
    status_code = 401
    code = "unauthenticated"


class AuthorizationError(DomainError):
    status_code = 403
    code = "forbidden"


class PrincipalKind(StrEnum):
    STAFF = "staff"
    CUSTOMER = "customer"
    SERVICE = "service"


@dataclass(frozen=True)
class Principal:
    """Who is making this request.

    `tenant_ids` is the authorization boundary: a principal may only act on a
    tenant present in this list, regardless of what the URL asks for.
    """

    subject_id: UUID
    kind: PrincipalKind
    tenant_ids: frozenset[UUID] = field(default_factory=frozenset)
    roles: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_staff(self) -> bool:
        return self.kind in (PrincipalKind.STAFF, PrincipalKind.SERVICE)

    def can_access_tenant(self, tenant_id: UUID) -> bool:
        # A service principal is trusted platform-internal machinery (workers,
        # webhook processors) and is not scoped to one tenant.
        if self.kind is PrincipalKind.SERVICE:
            return True

        # A customer may transact with any salon on the platform, including one
        # they have never visited. NOVA is a marketplace: requiring a prior
        # relationship before the first booking is a contradiction, and it was
        # a real one — `_issue_pair` assigns kind=CUSTOMER exactly when a user
        # has no memberships, so every customer principal was refused by every
        # tenant-scoped route and self-service booking had no working path.
        #
        # Reaching a tenant is therefore no longer the same as having authority
        # within it. `require_staff` guards operational routes, and per-row
        # ownership checks guard the rest — see `BookingService.get_for_principal`
        # and its callers. This line is only safe because those exist.
        if self.kind is PrincipalKind.CUSTOMER:
            return True

        return tenant_id in self.tenant_ids


ACCESS_TOKEN_TTL_SECONDS = 15 * 60
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 3600


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def issue_token(
    *,
    subject_id: UUID,
    kind: PrincipalKind,
    secret: str,
    tenant_ids: frozenset[UUID] | set[UUID] | None = None,
    roles: frozenset[str] | set[str] | None = None,
    token_version: int = 0,
    ttl_seconds: int = ACCESS_TOKEN_TTL_SECONDS,
    token_type: str = "access",
) -> str:
    """Mints an HS256 token.

    Access tokens are short-lived (15 minutes). `token_version` is embedded, and
    `get_principal` compares it with the account's on every request, so bumping
    `User.token_version` ends every outstanding token at once.

    Tenant memberships are baked in at issue time, which is why the issuer
    must read them from the `memberships` table and never from client input.
    """
    now = int(time.time())
    claims = {
        "sub": str(subject_id),
        "kind": str(kind),
        "tenants": sorted(str(t) for t in (tenant_ids or ())),
        "roles": sorted(roles or ()),
        "ver": token_version,
        "typ": token_type,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps(claims).encode())
    signature = hmac.new(secret.encode(), f"{header}.{payload}".encode(), sha256).digest()
    return f"{header}.{payload}.{_b64url_encode(signature)}"


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _json_object(segment: str) -> dict:
    """One token segment as a JSON object, or AuthenticationError.

    Anything else is refused here: read as a dict, a JSON array's missing
    `.get` raised AttributeError, a 500 any anonymous caller could trigger.
    `ValueError` covers bad base64, bad UTF-8 and bad JSON; `RecursionError`
    covers JSON nested past the parser's limit.
    """
    try:
        value = json.loads(_b64url_decode(segment))
    except (ValueError, RecursionError) as exc:
        raise AuthenticationError("Malformed token.") from exc
    if not isinstance(value, dict):
        raise AuthenticationError("Malformed token.")
    return value


def decode_token(token: str, *, secret: str, leeway_seconds: int = 0) -> dict:
    """Verifies an HS256 JWT and returns its claims.

    Raises AuthenticationError for anything malformed, forged, or expired. The
    claims are parsed only after the signature proves this server wrote them.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthenticationError("Malformed token.")

    header_b64, payload_b64, signature_b64 = parts
    header = _json_object(header_b64)

    # Pin the algorithm. Trusting header["alg"] is how "alg: none" forgeries work.
    if header.get("alg") != "HS256":
        raise AuthenticationError("Unsupported token algorithm.")

    try:
        signature = _b64url_decode(signature_b64)
    except ValueError as exc:
        raise AuthenticationError("Malformed token.") from exc
    expected = hmac.new(secret.encode(), f"{header_b64}.{payload_b64}".encode(), sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise AuthenticationError("Invalid token signature.")

    claims = _json_object(payload_b64)

    expiry = claims.get("exp")
    if expiry is None:
        raise AuthenticationError("Token has no expiry.")
    # A NumericDate. Python's JSON reads NaN and Infinity, and NaN compares
    # false with everything, so a token expiring at NaN would never expire.
    if isinstance(expiry, bool) or not isinstance(expiry, int | float) or not math.isfinite(expiry):
        raise AuthenticationError("Token expiry is invalid.")

    issued_at = claims.get("iat")
    if (
        isinstance(issued_at, bool)
        or not isinstance(issued_at, int | float)
        or not math.isfinite(issued_at)
    ):
        raise AuthenticationError("Token has no valid issue time.")
    # However far out `exp` claims to be, it did not get there from anything
    # this app mints: every token type here (access, refresh, and the
    # purpose tokens below) has `exp - iat` well under REFRESH_TOKEN_TTL_
    # SECONDS, the longest-lived one. A forged token — possible only with
    # the signing key itself (TM-03) — is bounded to that regardless of what
    # its forger set `exp` to.
    if expiry - issued_at > REFRESH_TOKEN_TTL_SECONDS:
        raise AuthenticationError("Token lifetime exceeds the maximum allowed.")

    if time.time() > expiry + leeway_seconds:
        raise AuthenticationError("Token has expired.")

    return claims


def purpose_key(secret: str, purpose: str) -> str:
    """Derives a signing key for one narrow purpose from the root secret.

    docs/14 TM-03's own fix sketch: "derive a key per purpose from the root
    key". A token signed with `purpose_key(secret, "phone_verification")`
    does not verify against the plain root secret, and vice versa — so even
    if a purpose-token secret were somehow exposed on its own, it would not
    forge an access token, and a leaked access-token flow does not touch
    this derivation at all. Still HMAC-SHA256 under the hood (ADR-0006's
    stdlib-only choice), just keyed differently per purpose.
    """
    return hmac.new(secret.encode(), f"nova:{purpose}".encode(), sha256).hexdigest()


def issue_purpose_token(*, subject_id: UUID, purpose: str, secret: str, ttl_seconds: int) -> str:
    """Mints a single-purpose JWT: no `kind`, no `tenants`, no `roles`.

    For actions that need to prove *something narrow* about one account —
    "this request came from whoever controls this session" — rather than
    reissue the full `Principal` shape `issue_token` mints. Signed with
    `purpose_key`, not the root secret, and `typ` is `purpose` itself, so
    `get_principal` already refuses one of these outright (it only accepts
    `typ="access"`) without any extra code — see practice #7 of
    https://curity.io/resources/learn/jwt-best-practices/: a token minted for
    one job must not be usable as another.

    Carries nothing beyond `sub`, `typ`, `jti` and the time claims — no PII,
    no business data. Whatever channel a purpose token travels over (a
    WhatsApp message, for phone verification) is a front channel exactly in
    that article's sense: readable by the messaging provider, visible in a
    lock-screen notification preview, sitting in chat history. A claim that
    would be sensitive on that channel does not belong in the token; look it
    up server-side from `sub` instead.
    """
    now = int(time.time())
    claims = {
        "sub": str(subject_id),
        "typ": purpose,
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + ttl_seconds,
    }
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps(claims).encode())
    key = purpose_key(secret, purpose)
    signature = hmac.new(key.encode(), f"{header}.{payload}".encode(), sha256).digest()
    return f"{header}.{payload}.{_b64url_encode(signature)}"


def decode_purpose_token(token: str, *, purpose: str, secret: str) -> dict:
    """Verifies a token minted by `issue_purpose_token` for exactly `purpose`.

    Refuses a token minted for any other purpose (including a stolen access
    or refresh token) with the same `AuthenticationError` a bad signature
    gets — there is nothing useful in distinguishing "wrong purpose" from
    "forged" to whoever presents one.
    """
    claims = decode_token(token, secret=purpose_key(secret, purpose))
    if claims.get("typ") != purpose:
        raise AuthenticationError("Token was not issued for this purpose.")
    return claims


def _principal_from_claims(claims: dict) -> Principal:
    try:
        return Principal(
            subject_id=UUID(claims["sub"]),
            kind=PrincipalKind(claims.get("kind", PrincipalKind.CUSTOMER)),
            tenant_ids=frozenset(UUID(t) for t in claims.get("tenants", [])),
            roles=frozenset(claims.get("roles", [])),
        )
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise AuthenticationError("Token claims are invalid.") from exc


@dataclass(frozen=True)
class TokenState:
    """What an account's tokens are checked against on every request."""

    token_version: int
    is_active: bool


#: Reads an account's current `TokenState`, or None when there is no such account.
TokenStateLookup = Callable[[UUID], Awaitable[TokenState | None]]

_TOKEN_STATE_SQL = text("SELECT token_version, is_active FROM users WHERE id = :id")


async def token_state_in(session: AsyncSession, subject_id: UUID) -> TokenState | None:
    """The account's token version and status, read through `session`.

    Raw SQL rather than identity's `User` model, because core imports no module.
    `users` has no row-level security, so no tenant scope is needed.
    """
    row = (await session.execute(_TOKEN_STATE_SQL, {"id": subject_id})).first()
    if row is None:
        return None
    return TokenState(token_version=row.token_version, is_active=row.is_active)


async def read_token_state(subject_id: UUID) -> TokenState | None:
    """`token_state_in`, in a session of its own that closes before the route runs.

    Not the request session: the AI chat holds no request transaction, and this
    must not open one for it. One primary-key read per authenticated request.
    """
    async with get_session_factory()() as session:
        return await token_state_in(session, subject_id)


def get_token_state_lookup() -> TokenStateLookup:
    """The account reader `get_principal` uses. Tests override it."""
    return read_token_state


def _dev_bypass_principal(settings: Settings) -> Principal | None:
    """Local-only escape hatch.

    `Settings` already refuses to load in any state `dev_bypass_refusal`
    rejects. The rule is checked again here, so settings built without
    validation cannot reopen it.
    """
    if not settings.auth_dev_bypass:
        return None
    refusal = dev_bypass_refusal(settings)
    if refusal is not None:
        # Fail loudly rather than silently disabling auth.
        raise AuthenticationError(f"{refusal} Refusing to serve.")
    return Principal(
        subject_id=UUID("00000000-0000-0000-0000-000000000001"),
        kind=PrincipalKind.SERVICE,
        roles=frozenset({"dev"}),
    )


def _service_kind_refusal(env: str) -> str | None:
    """Why a bearer token naming `kind=service` may not authenticate, or None.

    `_issue_pair` mints STAFF or CUSTOMER only, and the dev bypass builds its
    SERVICE principal directly, without a token at all — so the app itself
    never puts `kind=service` on a bearer token. One naming it anyway proves
    nothing but possession of `SECRET_KEY`, and that principal skips
    `_assert_token_is_current` below, since it names no account to re-check:
    a leaked key would otherwise mint permanent, unrevocable access to every
    tenant (docs/14 TM-03). Honoured only where the dev bypass itself is.
    """
    if env in DEVELOPMENT_ENVS:
        return None
    return "Service principals do not authenticate over a bearer token."


async def _assert_token_is_current(
    principal: Principal, claims: dict, lookup: TokenStateLookup
) -> None:
    """Refuses a token its account has since revoked.

    The checks `AuthService.refresh` makes, made on every request. Without them
    a logout-everywhere, a revoked membership or a deactivated account left
    every access token already issued working for up to 15 minutes.
    """
    state = await lookup(principal.subject_id)
    if state is None or not state.is_active:
        raise AuthenticationError("Account is no longer active.")
    if claims.get("ver", 0) != state.token_version:
        raise AuthenticationError("Token has been revoked.")


async def get_principal(
    request: Request, token_state: TokenStateLookup = Depends(get_token_state_lookup)
) -> Principal:
    """Authenticates the request. Fails closed.

    A staff or customer token must still match its account. A service token
    names no account, so has nothing to check; only a holder of `SECRET_KEY`
    can mint one.
    """
    settings = get_settings()

    header = request.headers.get("Authorization", "")
    if not header:
        bypass = _dev_bypass_principal(settings)
        if bypass is not None:
            return bypass
        raise AuthenticationError("Missing Authorization header.")

    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationError("Expected 'Authorization: Bearer <token>'.")

    claims = decode_token(token, secret=settings.secret_key)

    # A refresh token is long-lived; accepting one here would turn a stolen
    # refresh token into 30 days of API access.
    if claims.get("typ", "access") != "access":
        raise AuthenticationError("Refresh tokens cannot be used to call the API.")

    principal = _principal_from_claims(claims)
    if principal.kind is PrincipalKind.SERVICE:
        refusal = _service_kind_refusal(settings.env)
        if refusal is not None:
            raise AuthenticationError(refusal)
    else:
        await _assert_token_is_current(principal, claims, token_state)
    return principal


async def require_tenant_access(
    tenant_id: UUID = Path(...),
    principal: Principal = Depends(get_principal),
) -> UUID:
    """Resolves the active tenant AND proves the caller may act on it.

    Replaces the old `get_tenant_context`, which returned the path value with
    no check at all. `tenant_id` still comes only from the path — never the
    body or a query parameter — so a request cannot widen its own scope.
    """
    if not principal.can_access_tenant(tenant_id):
        # 403, not 404: the caller authenticated, they are simply not permitted.
        raise AuthorizationError("You do not have access to this tenant.")
    return tenant_id


async def require_staff(principal: Principal = Depends(get_principal)) -> Principal:
    if not principal.is_staff:
        raise AuthorizationError("This action requires staff access.")
    return principal
