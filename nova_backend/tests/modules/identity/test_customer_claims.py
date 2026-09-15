"""A phone number claims an existing customer record only once verified.

docs/14 TM-01: before this, `CustomerService.ensure_for_user` matched an
existing, unclaimed walk-in record by phone alone. Registering with someone
else's number read their booking history immediately (the claim itself was
never committed on a read) and, on any committing self-service path,
permanently took over their identity at that salon — proven live against the
running stack on 2026-09-15.

Verification is a short-lived, purpose-signed JWT sent over WhatsApp
(`security.issue_purpose_token` / `decode_purpose_token`), not a numeric
one-time code in a database table — see `AuthService.request_phone_
verification`. Needs Postgres, for the same reason `test_token_revocation.py`
does: this runs the real `AuthService` path, not a stubbed one.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import RateLimiter
from app.core.security import PrincipalKind, issue_purpose_token, issue_token
from app.db.session import set_tenant_scope
from app.modules.identity.auth_service import (
    PHONE_VERIFY_PURPOSE,
    AuthService,
    InvalidVerificationTokenError,
)
from app.modules.identity.exceptions import (
    CustomerPhoneRequiredError,
    PhoneVerificationRequiredError,
)
from app.modules.identity.models import Tenant, User
from app.modules.identity.repository import CustomerRepository
from app.modules.identity.service import CustomerService

PHONE = "+966501112222"
SECRET = "test-secret"


class _RecordingWhatsAppClient:
    """Captures the token instead of calling out, so the test can read it."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_template_message(
        self, *, to_phone: str, template_name: str, params: dict[str, str], language: str = "ar"
    ) -> str:
        self.sent.append({"to_phone": to_phone, "template_name": template_name, "params": params})
        return "fake-message-id"


@pytest.fixture
def whatsapp() -> _RecordingWhatsAppClient:
    return _RecordingWhatsAppClient()


@pytest.fixture
def auth(db_session: AsyncSession, whatsapp: _RecordingWhatsAppClient) -> AuthService:
    return AuthService(db_session, secret_key=SECRET, limiter=RateLimiter(), whatsapp=whatsapp)


@pytest.fixture
async def customers(db_session: AsyncSession, tenant: Tenant) -> CustomerService:
    # No `client`/`get_tenant_context` here — this test drives the service
    # directly, so it has to scope the connection's RLS itself.
    await set_tenant_scope(db_session, tenant.id)
    return CustomerService(
        CustomerRepository(db_session, tenant.id),
        tenant_id=tenant.id,
        allowed_phone_country_codes=["966"],
    )


@pytest.fixture
async def tenant(tenant_factory) -> Tenant:
    return await tenant_factory()


@pytest.fixture
async def caller(db_session: AsyncSession) -> User:
    user = User(
        email=f"caller-{uuid4().hex[:8]}@example.com",
        full_name="Caller",
        password_hash="not-a-real-hash",
        phone=PHONE,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _walk_in(as_owner, db_session: AsyncSession, tenant: Tenant, *, phone: str = PHONE):
    from app.modules.identity.models import Customer

    async with as_owner():
        record = Customer(
            tenant_id=tenant.id, full_name="Victim", phone=phone, notes="confidential note"
        )
        db_session.add(record)
        await db_session.flush()
    return record


async def test_an_unverified_phone_cannot_claim_an_existing_record(
    customers: CustomerService, caller: User, as_owner, db_session: AsyncSession, tenant: Tenant
) -> None:
    walk_in = await _walk_in(as_owner, db_session, tenant)

    with pytest.raises(PhoneVerificationRequiredError):
        await customers.ensure_for_user(caller)

    await db_session.refresh(walk_in)
    assert walk_in.user_id is None, "the read must not have committed a claim"


async def test_a_verified_phone_claims_the_matching_unclaimed_record(
    customers: CustomerService,
    auth: AuthService,
    caller: User,
    whatsapp: _RecordingWhatsAppClient,
    as_owner,
    db_session: AsyncSession,
    tenant: Tenant,
) -> None:
    walk_in = await _walk_in(as_owner, db_session, tenant)

    await auth.request_phone_verification(caller.id)
    token = whatsapp.sent[0]["params"]["token"]
    await auth.confirm_phone_verification(caller.id, token)

    claimed = await customers.ensure_for_user(caller)

    assert claimed.id == walk_in.id
    assert claimed.user_id == caller.id
    assert claimed.notes == "confidential note"


async def test_a_verified_phone_that_matches_nothing_creates_a_fresh_record(
    customers: CustomerService,
    auth: AuthService,
    caller: User,
    whatsapp: _RecordingWhatsAppClient,
) -> None:
    """Verification does not require a pre-existing record to link to."""
    await auth.request_phone_verification(caller.id)
    token = whatsapp.sent[0]["params"]["token"]
    await auth.confirm_phone_verification(caller.id, token)

    created = await customers.ensure_for_user(caller)

    assert created.phone == PHONE
    assert created.user_id == caller.id


async def test_ensure_for_user_is_idempotent_once_claimed(
    customers: CustomerService,
    auth: AuthService,
    caller: User,
    whatsapp: _RecordingWhatsAppClient,
    as_owner,
    db_session: AsyncSession,
    tenant: Tenant,
) -> None:
    walk_in = await _walk_in(as_owner, db_session, tenant)
    await auth.request_phone_verification(caller.id)
    token = whatsapp.sent[0]["params"]["token"]
    await auth.confirm_phone_verification(caller.id, token)
    await customers.ensure_for_user(caller)

    again = await customers.ensure_for_user(caller)

    assert again.id == walk_in.id


async def test_a_caller_with_no_phone_is_refused_regardless(
    customers: CustomerService, db_session: AsyncSession
) -> None:
    phoneless = User(
        email=f"nophone-{uuid4().hex[:8]}@example.com",
        full_name="No Phone",
        password_hash="not-a-real-hash",
    )
    db_session.add(phoneless)
    await db_session.flush()

    with pytest.raises(CustomerPhoneRequiredError):
        await customers.ensure_for_user(phoneless)


async def test_an_already_claimed_number_is_a_conflict_even_once_verified(
    customers: CustomerService,
    auth: AuthService,
    caller: User,
    whatsapp: _RecordingWhatsAppClient,
    as_owner,
    db_session: AsyncSession,
    tenant: Tenant,
) -> None:
    """Verifying your own number does not let you take someone else's already
    -linked record — only an *unclaimed* one is up for grabs."""
    from app.modules.identity.exceptions import DuplicatePhoneError

    other_owner = User(
        email=f"owner2-{uuid4().hex[:8]}@example.com",
        full_name="Someone Else",
        password_hash="not-a-real-hash",
    )
    db_session.add(other_owner)
    await db_session.flush()
    async with as_owner():
        from app.modules.identity.models import Customer

        already_linked = Customer(
            tenant_id=tenant.id, full_name="Someone Else", phone=PHONE, user_id=other_owner.id
        )
        db_session.add(already_linked)
        await db_session.flush()

    await auth.request_phone_verification(caller.id)
    token = whatsapp.sent[0]["params"]["token"]
    await auth.confirm_phone_verification(caller.id, token)

    with pytest.raises(DuplicatePhoneError):
        await customers.ensure_for_user(caller)


# --- JWT-specific properties (not reachable with a numeric OTP) -----------


async def test_a_token_minted_for_a_different_account_does_not_verify_this_one(
    auth: AuthService, caller: User, whatsapp: _RecordingWhatsAppClient
) -> None:
    """The signature alone is not enough — `sub` must match the caller too,
    or a token that leaked from someone else's WhatsApp thread would verify
    whichever account happens to present it."""
    someone_elses_token = issue_purpose_token(
        subject_id=uuid4(), purpose=PHONE_VERIFY_PURPOSE, secret=SECRET, ttl_seconds=600
    )

    with pytest.raises(InvalidVerificationTokenError):
        await auth.confirm_phone_verification(caller.id, someone_elses_token)


async def test_a_token_minted_for_another_purpose_is_refused(
    auth: AuthService, caller: User
) -> None:
    """A real access token — or any token not minted with `typ="phone_
    verification"` — must not double as a phone-verification credential
    (Curity JWT best practice #7: a token minted for one job must not work
    as another)."""
    an_access_token = issue_token(subject_id=caller.id, kind=PrincipalKind.CUSTOMER, secret=SECRET)

    with pytest.raises(InvalidVerificationTokenError):
        await auth.confirm_phone_verification(caller.id, an_access_token)


async def test_an_expired_verification_token_is_refused(
    auth: AuthService, caller: User
) -> None:
    expired = issue_purpose_token(
        subject_id=caller.id, purpose=PHONE_VERIFY_PURPOSE, secret=SECRET, ttl_seconds=-1
    )

    with pytest.raises(InvalidVerificationTokenError):
        await auth.confirm_phone_verification(caller.id, expired)


async def test_confirming_needs_no_prior_request_in_this_process(
    auth: AuthService, caller: User
) -> None:
    """Verification is a pure signature check with no server-side row behind
    it — a token minted independently of `request_phone_verification` (same
    secret, same shape) verifies exactly the same way. There is nothing to
    have "forgotten" to store."""
    token = issue_purpose_token(
        subject_id=caller.id, purpose=PHONE_VERIFY_PURPOSE, secret=SECRET, ttl_seconds=600
    )

    await auth.confirm_phone_verification(caller.id, token)

    assert caller.phone_verified_at is not None
