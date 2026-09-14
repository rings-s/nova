"""Rate limiting.

ADR-0006 left token brute-forcing unthrottled. This adds a sliding-window
counter, applied hardest to the endpoints that matter: login and refresh.

Algorithm — sliding window log, implemented as a Redis sorted set:
  - each request adds a timestamped member,
  - members older than the window are trimmed,
  - the remaining count is the current rate.

Chosen over a fixed window because a fixed window lets a caller send 2x the
limit across a boundary (all of it in the last second of one window and the
first of the next). Chosen over a leaky bucket because the sorted set gives an
exact `retry_after` for free.

Redis is the backend so the limit is shared across API processes. When Redis
is unavailable the limiter falls back to a per-process in-memory window: less
accurate under horizontal scaling, but it fails *closed* on the limit rather
than disabling protection entirely.
"""

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitPolicy:
    limit: int
    window_seconds: int

    @property
    def description(self) -> str:
        return f"{self.limit} requests per {self.window_seconds}s"


#: Tight: an attacker guessing passwords should get very few attempts, and a
#: legitimate user never needs more.
LOGIN_POLICY = RateLimitPolicy(limit=5, window_seconds=60)
#: Refresh is automated, so it is called more often than login but still rarely.
REFRESH_POLICY = RateLimitPolicy(limit=20, window_seconds=60)
#: General API traffic.
DEFAULT_POLICY = RateLimitPolicy(limit=120, window_seconds=60)
#: Writes are more expensive than reads.
WRITE_POLICY = RateLimitPolicy(limit=40, window_seconds=60)

# --- public marketplace (ADR-0010) ---------------------------------------
#
# Discovery is unauthenticated, so there is no principal to bucket by and every
# limit below is per IP. That is a weaker control than the authenticated
# routes get — one caller behind many addresses evades it — so these numbers
# are set to bound scraping rather than to prevent it.

#: Browsing. Generous, because a customer legitimately pages through results
#: and refines a query several times in a minute.
DISCOVERY_POLICY = RateLimitPolicy(limit=60, window_seconds=60)

#: Tighter, and deliberately the tightest read on the platform. Free slots are
#: the inverse of a provider's calendar, so this endpoint answers "when is
#: Sara busy" to anyone patient enough to sweep a date range. A customer
#: picking a time needs a handful of calls; a scraper needs thousands.
DISCOVERY_AVAILABILITY_POLICY = RateLimitPolicy(limit=20, window_seconds=60)

#: Recording a click. One per storefront opened, so a real customer stays far
#: below this while a loop inflating referral counts does not.
DISCOVERY_REFERRAL_POLICY = RateLimitPolicy(limit=10, window_seconds=60)


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class RateLimiter:
    """Sliding-window limiter over Redis, with an in-process fallback."""

    def __init__(self, redis_client=None) -> None:
        self._redis = redis_client
        self._memory: dict[str, deque[float]] = defaultdict(deque)

    async def check(self, key: str, policy: RateLimitPolicy) -> RateLimitResult:
        now = time.time()
        if self._redis is not None:
            try:
                return await self._check_redis(key, policy, now)
            except Exception:
                # Never let a Redis outage take the API down. Degrade to the
                # local window and say so once per occurrence.
                logger.warning("rate_limit_redis_unavailable", exc_info=True)
        return self._check_memory(key, policy, now)

    async def _check_redis(self, key: str, policy: RateLimitPolicy, now: float) -> RateLimitResult:
        window_start = now - policy.window_seconds
        redis_key = f"ratelimit:{key}"

        # One round trip, and each command is atomic within the pipeline.
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zadd(redis_key, {f"{now}:{id(self)}": now})
        pipe.zcard(redis_key)
        pipe.expire(redis_key, policy.window_seconds + 1)
        _, _, count, _ = await pipe.execute()

        if count > policy.limit:
            oldest = await self._redis.zrange(redis_key, 0, 0, withscores=True)
            retry_after = 1
            if oldest:
                retry_after = max(1, int(oldest[0][1] + policy.window_seconds - now) + 1)
            return RateLimitResult(False, 0, retry_after)

        return RateLimitResult(True, max(0, policy.limit - count), 0)

    def _check_memory(self, key: str, policy: RateLimitPolicy, now: float) -> RateLimitResult:
        window_start = now - policy.window_seconds
        bucket = self._memory[key]

        while bucket and bucket[0] < window_start:
            bucket.popleft()

        if len(bucket) >= policy.limit:
            retry_after = max(1, int(bucket[0] + policy.window_seconds - now) + 1)
            return RateLimitResult(False, 0, retry_after)

        bucket.append(now)
        return RateLimitResult(True, policy.limit - len(bucket), 0)

    def reset(self, key: str | None = None) -> None:
        """Test helper: clears the in-memory window."""
        if key is None:
            self._memory.clear()
        else:
            self._memory.pop(key, None)


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter(_build_redis_client())
    return _limiter


def _build_redis_client():
    try:
        from redis.asyncio import Redis

        from app.core.config import get_settings

        return Redis.from_url(str(get_settings().redis_url), decode_responses=True)
    except Exception:
        logger.warning("rate_limit_redis_client_unavailable", exc_info=True)
        return None
