"""FastAPI dependencies that apply rate-limit policies to endpoints."""

import ipaddress

from fastapi import Depends, Request

from app.core.config import get_settings
from app.core.rate_limit import (
    DEFAULT_POLICY,
    DISCOVERY_AVAILABILITY_POLICY,
    DISCOVERY_PHOTO_POLICY,
    DISCOVERY_POLICY,
    DISCOVERY_REFERRAL_POLICY,
    LOGIN_POLICY,
    REFRESH_POLICY,
    WRITE_POLICY,
    RateLimitExceeded,
    RateLimitPolicy,
    get_rate_limiter,
)
from app.core.security import Principal, get_principal


def client_ip_key(request: Request) -> str:
    """The caller's address, as the bucket an IP rate limit charges.

    `X-Forwarded-For` is never read. Cloudflare appends to a header the client
    already sent, so its first entry is whatever the client wrote, and trusting
    it gave every request a fresh bucket. The one header trusted is the one
    `Settings.trusted_client_ip_header` names, which the proxy in front of the
    API writes itself. Without one, the TCP peer is the caller.

    IPv6 is bucketed by /64, the block one subscriber is routinely given, so an
    attacker cannot take a new bucket for every address inside it.
    """
    header = get_settings().trusted_client_ip_header
    address = _parse_ip(request.headers.get(header)) if header else None
    if address is None:
        address = _parse_ip(request.client.host if request.client else None)
    if address is None:
        return "unknown"
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.IPv6Network((address, 64), strict=False))
    return str(address)


def _parse_ip(value: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not value:
        return None
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def rate_limit(policy: RateLimitPolicy, *, scope: str):
    """Builds a dependency enforcing `policy`, bucketed by `scope`."""

    async def _dependency(request: Request) -> None:
        limiter = get_rate_limiter()
        key = f"{scope}:{client_ip_key(request)}"
        result = await limiter.check(key, policy)
        if not result.allowed:
            raise RateLimitExceeded(result.retry_after_seconds, policy)

    return _dependency


def rate_limit_by_principal(policy: RateLimitPolicy, *, scope: str):
    """Limits per authenticated principal rather than per IP.

    Fairer once a caller is known: several staff behind one salon's NAT get
    their own budgets instead of competing for a shared one.
    """

    async def _dependency(request: Request, principal: Principal = Depends(get_principal)) -> None:
        limiter = get_rate_limiter()
        key = f"{scope}:{principal.subject_id}"
        result = await limiter.check(key, policy)
        if not result.allowed:
            raise RateLimitExceeded(result.retry_after_seconds, policy)

    return _dependency


login_rate_limit = rate_limit(LOGIN_POLICY, scope="login")
refresh_rate_limit = rate_limit(REFRESH_POLICY, scope="refresh")
default_rate_limit = rate_limit(DEFAULT_POLICY, scope="api")
write_rate_limit = rate_limit_by_principal(WRITE_POLICY, scope="write")

# Public marketplace routes. Necessarily `rate_limit` and not
# `rate_limit_by_principal` — there is no principal on an anonymous request,
# and depending on one would turn every discovery route into a 401.
discovery_read_rate_limit = rate_limit(DISCOVERY_POLICY, scope="discovery")
discovery_availability_rate_limit = rate_limit(
    DISCOVERY_AVAILABILITY_POLICY, scope="discovery-availability"
)
discovery_referral_rate_limit = rate_limit(DISCOVERY_REFERRAL_POLICY, scope="discovery-referral")
discovery_photo_rate_limit = rate_limit(DISCOVERY_PHOTO_POLICY, scope="discovery-photo")
