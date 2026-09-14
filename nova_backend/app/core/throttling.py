"""FastAPI dependencies that apply rate-limit policies to endpoints."""

from fastapi import Depends, Request

from app.core.exceptions import DomainError
from app.core.rate_limit import (
    DEFAULT_POLICY,
    DISCOVERY_AVAILABILITY_POLICY,
    DISCOVERY_POLICY,
    DISCOVERY_REFERRAL_POLICY,
    LOGIN_POLICY,
    REFRESH_POLICY,
    WRITE_POLICY,
    RateLimitPolicy,
    get_rate_limiter,
)
from app.core.security import Principal, get_principal


class RateLimitExceeded(DomainError):
    status_code = 429
    code = "rate_limit_exceeded"

    def __init__(self, retry_after_seconds: int, policy: RateLimitPolicy) -> None:
        super().__init__(
            f"Rate limit exceeded ({policy.description}). Retry in {retry_after_seconds} seconds."
        )
        self.retry_after_seconds = retry_after_seconds


def _client_key(request: Request) -> str:
    """Identifies the caller for limiting purposes.

    Prefers the real client IP from `X-Forwarded-For`, which is what Cloudflare
    Tunnel sets — without it every request appears to come from the tunnel and
    the whole platform shares one bucket.

    Trusting that header is only safe because nothing reaches this service
    except through the tunnel (docs/01). If the API is ever exposed directly,
    this becomes spoofable and must move behind a trusted-proxy check.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(policy: RateLimitPolicy, *, scope: str):
    """Builds a dependency enforcing `policy`, bucketed by `scope`."""

    async def _dependency(request: Request) -> None:
        limiter = get_rate_limiter()
        key = f"{scope}:{_client_key(request)}"
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
