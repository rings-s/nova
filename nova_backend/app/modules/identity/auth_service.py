"""identity · APPLICATION layer — authentication use cases.

The token issuer ADR-0006 listed as missing. Tokens are minted here from the
`memberships` table, so `Principal.tenant_ids` reflects real grants rather than
anything a client asserted.
"""

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError, ValidationDomainError
from app.core.passwords import hash_password, needs_rehash, verify_password
from app.core.rate_limit import (
    LOGIN_FAILURE_POLICY,
    RateLimiter,
    RateLimitExceeded,
    RateLimitPolicy,
)
from app.core.security import (
    ACCESS_TOKEN_TTL_SECONDS,
    REFRESH_TOKEN_TTL_SECONDS,
    AuthenticationError,
    PrincipalKind,
    decode_purpose_token,
    decode_token,
    issue_purpose_token,
    issue_token,
)
from app.db.session import bypass_tenant_scope
from app.integrations.whatsapp.client import NotConfiguredWhatsAppClient, WhatsAppClient
from app.modules.identity.models import Membership, User

logger = logging.getLogger(__name__)

#: Consecutive failed logins at one account, from any address, before it locks.
#:
#: Well above `LOGIN_FAILURE_POLICY`, the allowance for one client at one
#: account, on purpose. A lock stops the owner too, so it is kept for guessing
#: spread across several addresses: one address runs out of attempts long before
#: it could lock anybody out on its own.
MAX_FAILED_LOGINS = 20
LOCKOUT_DURATION = timedelta(minutes=15)

#: docs/14 TM-01. A short-lived, purpose-signed JWT (`issue_purpose_token`),
#: not a numeric one-time code in a database table: verifying the signature
#: is the whole check, so there is nothing to hash, store, or count wrong
#: guesses against — a valid signature cannot be brute-forced in any
#: practical time, unlike a 6-digit code. The token is not tracked as
#: single-use: replaying it before it expires only re-confirms an already-
#: idempotent fact (`phone_verified_at`), so the state that would buy is not
#: worth keeping.
PHONE_VERIFY_PURPOSE = "phone_verification"
PHONE_VERIFY_TTL_SECONDS = 10 * 60
#: Per account, not per client address: the account owner is the one who
#: should be requesting these, however many devices they use, and an
#: attacker who can only see the account (never its phone) should not be
#: able to ring it with WhatsApp messages indefinitely.
PHONE_VERIFY_REQUEST_POLICY = RateLimitPolicy(limit=3, window_seconds=15 * 60)


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"

    def __init__(self) -> None:
        # Deliberately identical whether the email is unknown, the password is
        # wrong or the account is locked. Distinguishing them turns the login
        # form into an account enumeration oracle.
        super().__init__("Email or password is incorrect.")


class EmailAlreadyRegisteredError(DomainError):
    status_code = 409
    code = "email_already_registered"

    def __init__(self) -> None:
        super().__init__("That email address is already registered.")


class NoPhoneToVerifyError(ValidationDomainError):
    code = "no_phone_to_verify"

    def __init__(self) -> None:
        super().__init__("Add a phone number to your account before verifying it.")


class InvalidVerificationTokenError(ValidationDomainError):
    """One answer for wrong, expired, wrong-purpose, and missing — same
    reasoning as `InvalidCredentialsError`: distinguishing them tells a
    guesser which one they got right."""

    code = "invalid_verification_token"

    def __init__(self) -> None:
        super().__init__("That verification link or code is invalid or has expired.")


class TokenPair:
    __slots__ = ("access_token", "expires_in", "refresh_token", "token_type")

    def __init__(self, access_token: str, refresh_token: str) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_in = ACCESS_TOKEN_TTL_SECONDS
        self.token_type = "bearer"


def _email_digest(email: str) -> str:
    """Keys a limit to an account without writing the address into Redis."""
    return hashlib.sha256(email.encode()).hexdigest()[:32]


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        secret_key: str,
        limiter: RateLimiter,
        whatsapp: WhatsAppClient | None = None,
    ) -> None:
        self.session = session
        self.secret_key = secret_key
        self.limiter = limiter
        self.whatsapp = whatsapp or NotConfiguredWhatsAppClient()

    # --- registration ------------------------------------------------------

    async def register(
        self, *, email: str, password: str, full_name: str, phone: str | None = None
    ) -> User:
        email = email.strip().lower()

        if await self._find_by_email(email) is not None:
            raise EmailAlreadyRegisteredError()

        user = User(
            email=email,
            full_name=full_name,
            phone=phone,
            password_hash=hash_password(password),
        )
        self.session.add(user)
        await self.session.flush()
        return user

    # --- login -------------------------------------------------------------

    async def login(self, *, email: str, password: str, client_key: str) -> TokenPair:
        """Signs a user in, or refuses with one answer for every kind of failure.

        Three limits apply, each against a different attacker:

          - `login_rate_limit` caps how fast one client address tries anything
            (the router applies it);
          - `LOGIN_FAILURE_POLICY` stops one client address guessing at one
            account, without touching the owner signing in from anywhere else;
          - `MAX_FAILED_LOGINS` locks the account against guessing spread over
            many addresses.

        When this raises `InvalidCredentialsError` the caller must still commit.
        The failure count is the point of a failed attempt, and it used to roll
        back with the error, so no account ever locked.
        """
        email = email.strip().lower()
        failures = f"login-failures:{_email_digest(email)}:{client_key}"

        # Asked before the account is looked up, so an address with no account
        # is limited exactly like one with an account.
        allowance = await self.limiter.peek(failures, LOGIN_FAILURE_POLICY)
        if not allowance.allowed:
            raise RateLimitExceeded(allowance.retry_after_seconds, LOGIN_FAILURE_POLICY)

        try:
            user = await self._authenticate(email, password)
        except InvalidCredentialsError:
            await self.limiter.check(failures, LOGIN_FAILURE_POLICY)
            raise

        # Successful login clears the failure counts and opportunistically
        # upgrades a hash whose cost parameters are now below policy.
        user.failed_login_attempts = 0
        user.locked_until = None
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        await self.limiter.forget(failures)

        await self.session.flush()
        return await self._issue_pair(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        claims = decode_token(refresh_token, secret=self.secret_key)

        # A refresh token must not be usable as an access token, or a stolen
        # long-lived token would grant immediate API access.
        if claims.get("typ") != "refresh":
            raise AuthenticationError("Expected a refresh token.")

        user = await self.session.get(User, UUID(claims["sub"]))
        if user is None or not user.is_active:
            raise AuthenticationError("Account is no longer active.")

        # Rejects tokens minted before a logout-everywhere or password change.
        if claims.get("ver", 0) != user.token_version:
            raise AuthenticationError("Token has been revoked.")

        return await self._issue_pair(user)

    async def revoke_all_tokens(self, user_id: UUID) -> None:
        """Logout-everywhere. Invalidates every outstanding token at once."""
        user = await self.session.get(User, user_id)
        if user is not None:
            user.token_version += 1
            await self.session.flush()

    # --- phone verification (docs/14 TM-01) --------------------------------

    async def request_phone_verification(self, user_id: UUID) -> None:
        """Sends a short-lived, purpose-signed JWT to the account's own phone.

        Required before `CustomerService.ensure_for_user` will let a
        self-service booking claim an existing, unclaimed customer record by
        phone match — otherwise the claim rests on nothing but the caller's
        say-so. Rate-limited per account: the account owner is the one who
        should be asking, however many devices they use.

        No server-side row is written for the token itself — `decode_
        purpose_token` verifies it by signature alone, so there is nothing to
        invalidate here the way an OTP row would need clearing on a fresh
        request. A replay before expiry only re-confirms an already-true
        fact; see `PHONE_VERIFY_PURPOSE`'s comment above.
        """
        user = await self.session.get(User, user_id)
        if user is None or not user.phone:
            raise NoPhoneToVerifyError()

        allowance = await self.limiter.check(
            f"phone-verify-request:{user_id}", PHONE_VERIFY_REQUEST_POLICY
        )
        if not allowance.allowed:
            raise RateLimitExceeded(allowance.retry_after_seconds, PHONE_VERIFY_REQUEST_POLICY)

        token = issue_purpose_token(
            subject_id=user_id,
            purpose=PHONE_VERIFY_PURPOSE,
            secret=self.secret_key,
            ttl_seconds=PHONE_VERIFY_TTL_SECONDS,
        )
        # No PII in the WhatsApp message body beyond the token: the phone
        # number and account name stay server-side (Curity JWT best practice
        # #2 — a front-channel message should not carry sensitive data, and
        # the token itself carries none either, only `sub`/`typ`/`jti`/times).
        await self.whatsapp.send_template_message(
            to_phone=user.phone,
            template_name="phone_verification",
            params={"token": token},
        )

    async def confirm_phone_verification(self, user_id: UUID, token: str) -> None:
        """Marks the account's phone verified, if `token` is live and its own.

        Checking `claims["sub"] == user_id` (not just that the token is
        valid for *some* account) matters: without it, a token that leaked
        from one account's WhatsApp thread could verify a different,
        already-authenticated caller's phone instead of its own.
        """
        try:
            claims = decode_purpose_token(
                token, purpose=PHONE_VERIFY_PURPOSE, secret=self.secret_key
            )
        except AuthenticationError as exc:
            raise InvalidVerificationTokenError() from exc

        if claims.get("sub") != str(user_id):
            raise InvalidVerificationTokenError()

        user = await self.session.get(User, user_id)
        if user is not None:
            user.phone_verified_at = datetime.now(UTC)
        await self.session.flush()

    # --- internals ---------------------------------------------------------

    async def _authenticate(self, email: str, password: str) -> User:
        """The account these credentials open, or `InvalidCredentialsError`.

        Every refusal costs one password hash, so none answers measurably faster
        than another.
        """
        user = await self._find_by_email(email)
        if user is None:
            hash_password(password)
            raise InvalidCredentialsError()

        if user.locked_until is not None and user.locked_until > datetime.now(UTC):
            # No separate "locked" answer. It told anyone which addresses have an
            # account, and a correct password must not reveal that either.
            hash_password(password)
            raise InvalidCredentialsError()

        if not user.is_active or not verify_password(password, user.password_hash):
            await self._record_failed_login(user)
            raise InvalidCredentialsError()

        return user

    async def _find_by_email(self, email: str) -> User | None:
        stmt = select(User).where(func.lower(User.email) == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _record_failed_login(self, user: User) -> None:
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_LOGINS:
            user.locked_until = datetime.now(UTC) + LOCKOUT_DURATION
            # Starts the count again, so the next lock needs as many fresh
            # failures. Left at the threshold, one failure each time a lock
            # expired would have re-locked the account indefinitely.
            user.failed_login_attempts = 0
            logger.warning("account_locked", extra={"user_id": str(user.id)})
        await self.session.flush()

    async def _active_tenant_ids(self, user_id: UUID) -> frozenset[UUID]:
        stmt = select(Membership.tenant_id).where(
            Membership.user_id == user_id, Membership.is_active.is_(True)
        )
        result = await self.session.execute(stmt)
        return frozenset(result.scalars().all())

    async def _active_roles(self, user_id: UUID) -> frozenset[str]:
        stmt = select(Membership.role).where(
            Membership.user_id == user_id, Membership.is_active.is_(True)
        )
        result = await self.session.execute(stmt)
        return frozenset(str(r) for r in result.scalars().all())

    async def _issue_pair(self, user: User) -> TokenPair:
        # `memberships` carries the RLS policy from `d4e5f6a7b8c9`, and login
        # has no tenant to scope to — "which salons does this person belong
        # to?" is the question being asked. With the variable unset the policy
        # fails closed and matches nothing, so without this bypass every login
        # would mint a token with an empty `tenants` claim and every staff
        # member would authenticate as a customer.
        #
        # This is the one request path allowed to open it. It is bounded the
        # way the payment webhook's is: the two reads below select `tenant_id`
        # and `role` keyed by `user_id`, nothing else in this transaction
        # touches a tenant table, and `SET LOCAL` releases it at commit.
        await bypass_tenant_scope(self.session)

        tenant_ids = await self._active_tenant_ids(user.id)
        roles = await self._active_roles(user.id)

        # A user with no tenant membership is a customer; any membership makes
        # them staff for the tenants they belong to.
        kind = PrincipalKind.STAFF if tenant_ids else PrincipalKind.CUSTOMER

        common: dict[str, Any] = {
            "subject_id": user.id,
            "kind": kind,
            "secret": self.secret_key,
            "tenant_ids": tenant_ids,
            "roles": roles,
            "token_version": user.token_version,
        }
        return TokenPair(
            access_token=issue_token(
                **common, ttl_seconds=ACCESS_TOKEN_TTL_SECONDS, token_type="access"
            ),
            refresh_token=issue_token(
                **common, ttl_seconds=REFRESH_TOKEN_TTL_SECONDS, token_type="refresh"
            ),
        )
