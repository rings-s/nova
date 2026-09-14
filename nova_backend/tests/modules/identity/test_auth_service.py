"""Sign-in limits and lockout, against the database.

Needs Postgres. Each test gets its own in-process limiter, so no test shares a
bucket with another and none depends on Redis.

The router's half — committing a failed attempt so the count survives the error
— cannot show up here, because the test session is never rolled back between
the request and the assertion. It was checked against the running stack.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.passwords import hash_password
from app.core.rate_limit import LOGIN_FAILURE_POLICY, RateLimiter, RateLimitExceeded
from app.modules.identity.auth_service import (
    MAX_FAILED_LOGINS,
    AuthService,
    InvalidCredentialsError,
)
from app.modules.identity.models import User

PASSWORD = "correct-horse-battery"
ATTACKER = "198.51.100.7"
OWNER = "203.0.113.9"


@pytest.fixture
def auth(db_session: AsyncSession) -> AuthService:
    return AuthService(db_session, secret_key="auth-service-test-secret", limiter=RateLimiter())


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    account = User(
        email=f"owner-{uuid4().hex[:8]}@example.com",
        full_name="Salon Owner",
        password_hash=hash_password(PASSWORD),
    )
    db_session.add(account)
    await db_session.flush()
    return account


async def _fail(auth: AuthService, email: str, *, client: str, times: int) -> None:
    for attempt in range(times):
        with pytest.raises(InvalidCredentialsError):
            await auth.login(email=email, password=f"guess-{attempt}", client_key=client)


async def test_the_right_password_signs_in(auth: AuthService, user: User) -> None:
    tokens = await auth.login(email=user.email, password=PASSWORD, client_key=OWNER)
    assert tokens.access_token


async def test_a_locked_account_answers_like_a_wrong_password(
    auth: AuthService, user: User, db_session: AsyncSession
) -> None:
    """A separate "locked" answer told anyone which addresses had an account."""
    user.locked_until = datetime.now(UTC) + timedelta(minutes=5)
    await db_session.flush()

    with pytest.raises(InvalidCredentialsError):
        await auth.login(email=user.email, password=PASSWORD, client_key=OWNER)


async def test_one_client_runs_out_of_guesses_without_locking_the_owner_out(
    auth: AuthService, user: User
) -> None:
    await _fail(auth, user.email, client=ATTACKER, times=LOGIN_FAILURE_POLICY.limit)

    with pytest.raises(RateLimitExceeded):
        await auth.login(email=user.email, password=PASSWORD, client_key=ATTACKER)

    tokens = await auth.login(email=user.email, password=PASSWORD, client_key=OWNER)
    assert tokens.access_token


async def test_an_address_with_no_account_is_limited_the_same_way(auth: AuthService) -> None:
    email = f"nobody-{uuid4().hex[:8]}@example.com"
    await _fail(auth, email, client=ATTACKER, times=LOGIN_FAILURE_POLICY.limit)

    with pytest.raises(RateLimitExceeded):
        await auth.login(email=email, password="guess-again", client_key=ATTACKER)


async def test_signing_in_does_not_use_up_the_allowance(auth: AuthService, user: User) -> None:
    for _ in range(LOGIN_FAILURE_POLICY.limit + 2):
        await auth.login(email=user.email, password=PASSWORD, client_key=OWNER)


async def test_a_success_clears_the_clients_earlier_failures(auth: AuthService, user: User) -> None:
    await _fail(auth, user.email, client=OWNER, times=LOGIN_FAILURE_POLICY.limit - 1)
    await auth.login(email=user.email, password=PASSWORD, client_key=OWNER)

    # A full allowance again, not the one attempt that was left.
    await _fail(auth, user.email, client=OWNER, times=LOGIN_FAILURE_POLICY.limit - 1)
    await auth.login(email=user.email, password=PASSWORD, client_key=OWNER)


async def test_failures_spread_over_many_clients_lock_the_account(
    auth: AuthService, user: User, db_session: AsyncSession
) -> None:
    for attempt in range(MAX_FAILED_LOGINS):
        await _fail(auth, user.email, client=f"198.51.100.{attempt}", times=1)

    await db_session.refresh(user)
    assert user.locked_until is not None
    assert user.locked_until > datetime.now(UTC)
    with pytest.raises(InvalidCredentialsError):
        await auth.login(email=user.email, password=PASSWORD, client_key=OWNER)


async def test_each_lock_needs_a_fresh_run_of_failures(
    auth: AuthService, user: User, db_session: AsyncSession
) -> None:
    """Left at the threshold, one failure per expired lock re-locked it forever."""
    user.failed_login_attempts = MAX_FAILED_LOGINS - 1
    await db_session.flush()

    await _fail(auth, user.email, client=ATTACKER, times=1)

    await db_session.refresh(user)
    assert user.locked_until is not None
    assert user.failed_login_attempts == 0
