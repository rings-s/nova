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
  - It fails CLOSED. A missing or invalid token is 401 in every environment.
    The only bypass is an explicit local-development flag, and it refuses to
    engage outside `local`/`test` or on a stack a Cloudflare tunnel publishes.
"""

import base64
import hmac
import json
import time
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from fastapi import Depends, Path, Request

from app.core.config import Settings, dev_bypass_refusal, get_settings
from app.core.exceptions import DomainError


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

    Access tokens are short-lived (15 minutes) because they are stateless: a
    revoked one stays valid until it expires. `token_version` is embedded so
    bumping `User.token_version` invalidates every outstanding token at once.

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


def decode_token(token: str, *, secret: str, leeway_seconds: int = 0) -> dict:
    """Verifies an HS256 JWT and returns its claims.

    Raises AuthenticationError for anything malformed, forged, or expired.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthenticationError("Malformed token.")

    header_b64, payload_b64, signature_b64 = parts

    try:
        header = json.loads(_b64url_decode(header_b64))
        claims = json.loads(_b64url_decode(payload_b64))
        signature = _b64url_decode(signature_b64)
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthenticationError("Malformed token.") from exc

    # Pin the algorithm. Trusting header["alg"] is how "alg: none" forgeries work.
    if header.get("alg") != "HS256":
        raise AuthenticationError("Unsupported token algorithm.")

    expected = hmac.new(secret.encode(), f"{header_b64}.{payload_b64}".encode(), sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise AuthenticationError("Invalid token signature.")

    expiry = claims.get("exp")
    if expiry is None:
        raise AuthenticationError("Token has no expiry.")
    if time.time() > float(expiry) + leeway_seconds:
        raise AuthenticationError("Token has expired.")

    return claims


def _principal_from_claims(claims: dict) -> Principal:
    try:
        return Principal(
            subject_id=UUID(claims["sub"]),
            kind=PrincipalKind(claims.get("kind", PrincipalKind.CUSTOMER)),
            tenant_ids=frozenset(UUID(t) for t in claims.get("tenants", [])),
            roles=frozenset(claims.get("roles", [])),
        )
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Token claims are invalid.") from exc


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


async def get_principal(request: Request) -> Principal:
    """Authenticates the request. Fails closed."""
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

    return _principal_from_claims(claims)


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
