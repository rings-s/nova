"""Application layer for the identity module.

Use-case orchestration: validate via domain rules, load/persist via the
repository, emit events. Knows nothing about HTTP — the router translates.

Services flush but never commit. The request-scoped transaction is owned by
the router (see `app.core.deps.get_db_session`), so one endpoint can compose
several service calls into a single atomic unit.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.events import publish_event
from app.core.security import AuthorizationError, Principal, PrincipalKind
from app.core.validators import validate_email
from app.db.session import bypass_tenant_scope, set_tenant_scope
from app.modules.identity.domain import (
    MembershipRole,
    StaffPermission,
    generate_slug,
    may_manage_role,
    require_bilingual_text,
    role_allows,
    validate_gcc_phone,
)
from app.modules.identity.events import CustomerRegistered, TenantCreated
from app.modules.identity.exceptions import (
    CustomerNotFoundError,
    CustomerPhoneRequiredError,
    DuplicateMembershipError,
    DuplicatePhoneError,
    DuplicateSlugError,
    InsufficientRoleError,
    InvalidInviteError,
    LastOwnerError,
    MembershipNotFoundError,
    PhoneVerificationRequiredError,
    TenantNotFoundError,
)
from app.modules.identity.models import Customer, Membership, MembershipInvite, Tenant, User
from app.modules.identity.repository import (
    CustomerRepository,
    MembershipInviteRepository,
    MembershipRepository,
    TenantRepository,
    UserRepository,
)


def _hash_invite_token(token: str) -> str:
    """Hashes an invite token for storage.

    Unsalted, unlike a password hash: the token is 32 random bytes
    (`secrets.token_urlsafe(32)`, ~256 bits), so there is nothing short to
    precompute a table against. A salt defends against a small search space;
    this one has none.
    """
    return hashlib.sha256(token.encode()).hexdigest()


class TenantService:
    def __init__(
        self,
        repository: TenantRepository,
        *,
        memberships: MembershipRepository,
        allowed_phone_country_codes: list[str],
    ) -> None:
        self.repository = repository
        self.memberships = memberships
        self.allowed_phone_country_codes = allowed_phone_country_codes

    async def create(
        self,
        *,
        name_en: str,
        name_ar: str,
        phone: str,
        owner_user_id: UUID | None,
        default_currency: str = "SAR",
    ) -> Tenant:
        """Registers a business and makes the caller its owner.

        `owner_user_id` comes from the authenticated principal, never the
        request body — otherwise a caller could create a business owned by
        someone else. This endpoint was previously unauthenticated entirely, so
        anyone could create tenants anonymously.

        It is None only for a SERVICE principal (platform machinery, migrations,
        tests), which has no `users` row to reference and is not tenant-scoped
        anyway. A human caller always gets a membership — a business nobody can
        administer is not a useful thing to have created.

        The creator's existing access token does not carry the new tenant; they
        pick it up on their next `/auth/refresh`, within the 15-minute access
        token lifetime.
        """
        require_bilingual_text(name_en, name_ar)
        validate_gcc_phone(phone, self.allowed_phone_country_codes)
        slug = generate_slug(name_en)

        if await self.repository.get_by_slug(slug) is not None:
            raise DuplicateSlugError(slug)

        tenant = Tenant(
            name_en=name_en,
            name_ar=name_ar,
            slug=slug,
            phone=phone,
            default_currency=default_currency,
        )
        self.repository.add(tenant)
        await self.repository.session.flush()

        if owner_user_id is not None:
            # `memberships` is RLS-protected and this request carries no tenant
            # in its path, so nothing has set `app.current_tenant_id` yet — the
            # policy's WITH CHECK would reject the insert. The tenant now
            # exists and the caller is about to own it, so scope the rest of
            # the transaction to it rather than opening a bypass.
            await set_tenant_scope(self.repository.session, tenant.id)
            await self.memberships.grant(
                user_id=owner_user_id,
                tenant_id=tenant.id,
                role=MembershipRole.OWNER,
            )

        await publish_event(self.repository.session, TenantCreated(tenant_id=tenant.id))
        return tenant

    async def get(self, tenant_id: UUID) -> Tenant:
        tenant = await self.repository.get(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(tenant_id)
        return tenant

    async def list_for_principal(
        self, principal: Principal, *, limit: int = 20, offset: int = 0
    ) -> list[Tenant]:
        """The caller's own tenants.

        A service principal is platform-internal machinery and legitimately sees
        everything; a human sees only what their memberships grant.
        """
        if principal.kind is PrincipalKind.SERVICE:
            return await self.repository.list(limit=limit, offset=offset)
        return await self.repository.list_for_ids(principal.tenant_ids, limit=limit, offset=offset)


class CustomerService:
    """The people a salon books.

    Distinct from `User`: a walk-in reception types in has a customer record and
    no credentials, while a staff member has credentials and is not a customer.
    Someone booking themselves through the PWA is both, linked by `user_id`.
    """

    def __init__(
        self,
        repository: CustomerRepository,
        *,
        tenant_id: UUID,
        allowed_phone_country_codes: list[str],
        default_locale: str = "ar",
    ) -> None:
        self.repository = repository
        self.tenant_id = tenant_id
        self.allowed_phone_country_codes = allowed_phone_country_codes
        self.default_locale = default_locale

    @property
    def session(self):
        return self.repository.session

    async def create(
        self,
        *,
        full_name: str,
        phone: str,
        email: str | None = None,
        preferred_language: str | None = None,
        marketing_consent: bool = False,
        whatsapp_consent: bool = False,
        notes: str | None = None,
        user_id: UUID | None = None,
    ) -> Customer:
        validate_gcc_phone(phone, self.allowed_phone_country_codes)
        if email is not None:
            email = validate_email(email)

        if await self.repository.get_by_phone(phone) is not None:
            raise DuplicatePhoneError(phone)

        customer = Customer(
            tenant_id=self.tenant_id,
            user_id=user_id,
            full_name=full_name.strip(),
            phone=phone,
            email=email,
            preferred_language=preferred_language or self.default_locale,
            marketing_consent=marketing_consent,
            whatsapp_consent=whatsapp_consent,
            notes=notes,
        )
        self.repository.add(customer)
        await self.repository.session.flush()

        await publish_event(
            self.session,
            CustomerRegistered(
                tenant_id=self.tenant_id, customer_id=customer.id, phone=customer.phone
            ),
        )
        return customer

    async def get(self, customer_id: UUID) -> Customer:
        customer = await self.repository.get(customer_id)
        if customer is None:
            raise CustomerNotFoundError(customer_id)
        return customer

    async def find_by_phone(self, phone: str) -> Customer | None:
        return await self.repository.get_by_phone(phone)

    async def search(self, term: str, *, limit: int = 20, offset: int = 0) -> list[Customer]:
        return await self.repository.search(term, limit=limit, offset=offset)

    async def list(self, *, limit: int = 20, offset: int = 0) -> list[Customer]:
        return await self.repository.list(limit=limit, offset=offset)

    async def update_consent(
        self,
        customer_id: UUID,
        *,
        marketing_consent: bool | None = None,
        whatsapp_consent: bool | None = None,
    ) -> Customer:
        """PDPL: consent must be revocable as easily as it was given."""
        customer = await self.get(customer_id)
        if marketing_consent is not None:
            customer.marketing_consent = marketing_consent
        if whatsapp_consent is not None:
            customer.whatsapp_consent = whatsapp_consent
        await self.repository.session.flush()
        return customer

    async def resolve_for_booking(self, reference_id: UUID, *, self_service: bool) -> Customer:
        """Turns the authorization decision into an actual customer record.

        `booking.dependencies.resolve_booking_customer` decides *whose* booking
        this is and hands back an id; that id means two different things
        depending on how it was reached, and this is where the difference is
        resolved:

            self_service=True   the id is the caller's own *user* id, so find
                                or provision their customer record here
            self_service=False  staff named an existing *customer* id, so load
                                and tenant-check it

        Conflating the two is how a user id ends up in a customer_id column.
        """
        if not self_service:
            return await self.get(reference_id)

        user = await self.session.get(User, reference_id)
        if user is None:
            raise CustomerNotFoundError(reference_id)
        return await self.ensure_for_user(user)

    async def find_for_user(self, user_id: UUID) -> Customer | None:
        """This user's customer record at this tenant, or None.

        The read-only counterpart to `ensure_for_user`, and the distinction
        matters: authorization checks ask "is this row theirs?", and answering
        that by *provisioning* a customer record would let a failed permission
        check leave a row behind. Returns None rather than raising, because
        "this person has never visited this salon" is an ordinary answer.
        """
        return await self.repository.get_by_user_id(user_id)

    async def ensure_for_user(self, user: User) -> Customer:
        """The customer record for a signed-in person, creating it on first use.

        A customer booking themselves has an account but not necessarily a
        customer record at *this* salon — they may never have visited before.
        Rather than making the PWA call a separate "register me here" endpoint
        before every first booking, the first booking provisions it.

        Matched by `user_id` first, then by phone: if reception already typed
        this person in as a walk-in, that existing record is claimed rather than
        creating a duplicate that splits their history in two.

        The phone match is gated on `user.phone_verified_at` (docs/14 TM-01).
        Before this existed, registering with someone else's phone number
        claimed their unlinked customer record on the strength of that claim
        alone — no proof required — which read their booking history
        immediately and, on any committing self-service path, permanently
        took over their identity at that salon. `AuthService.
        request_phone_verification` / `confirm_phone_verification` are the
        way to earn the claim; an unverified number that already belongs to
        someone else's record falls through to `create()` below, which
        raises `DuplicatePhoneError` rather than silently duplicating or
        stealing it.
        """
        existing = await self.repository.get_by_user_id(user.id)
        if existing is not None:
            return existing

        if user.phone and user.phone_verified_at is not None:
            by_phone = await self.repository.get_unclaimed_by_phone(user.phone)
            if by_phone is not None:
                by_phone.user_id = user.id
                await self.repository.session.flush()
                return by_phone
        elif user.phone:
            # A record with this exact number may already exist — claimed or
            # not, staff-authored notes and all. Whether it does is exactly
            # the fact an unverified caller must not be able to read, so this
            # asks nothing and simply requires verification before proceeding.
            if await self.repository.get_by_phone(user.phone) is not None:
                raise PhoneVerificationRequiredError()

        if not user.phone:
            # Booking needs a reachable phone number for the ticket and the
            # WhatsApp confirmation; there is no sensible placeholder.
            raise CustomerPhoneRequiredError()

        return await self.create(
            full_name=user.full_name,
            phone=user.phone,
            email=user.email,
            user_id=user.id,
        )


class MembershipService:
    """Who works at this salon, and who may change that.

    Every method takes the acting `Principal` instead of trusting a route
    guard, because the authority question here cannot be answered by the
    token. `Principal.roles` is minted from every active membership a user
    holds across all tenants and flattened into one set with no tenant key, so
    an owner of salon A who also answers the phone at salon B carries
    `{"owner", "receptionist"}` at both. Checking that claim would let them
    administer salon B. The actor's role is therefore read from `memberships`
    for the tenant in hand, and `may_manage_role` decides from there.

    Row visibility is doubly bounded: this service is constructed from the
    authorized path tenant, and the same value has already scoped the
    connection for RLS.
    """

    #: How long an invite is redeemable. Generous — an owner inviting someone
    #: who is on leave should not have to reissue it — but not indefinite:
    #: a stale, forgotten invite is a standing credential nobody is watching.
    INVITE_TTL = timedelta(days=7)

    def __init__(
        self,
        repository: MembershipRepository,
        *,
        users: UserRepository,
        invites: MembershipInviteRepository,
        tenant_id: UUID,
    ) -> None:
        self.repository = repository
        self.users = users
        self.invites = invites
        self.tenant_id = tenant_id

    # `list_invites` is defined ahead of `list` below on purpose: a class-body
    # annotation naming the bare `list` type resolves against names already
    # bound in that class's namespace, and `list` (the method just below)
    # would otherwise shadow the builtin for every annotation after it.
    async def list_invites(
        self, principal: Principal, *, limit: int = 20, offset: int = 0
    ) -> list[MembershipInvite]:
        """Pending invites this tenant has sent — never their tokens."""
        await self._require_member(principal)
        return await self.invites.list_pending(self.tenant_id, limit=limit, offset=offset)

    async def list(
        self, principal: Principal, *, limit: int = 20, offset: int = 0
    ) -> list[Membership]:
        """The staff directory.

        Readable by any active member, not owners only: a receptionist needs to
        know which providers exist, and this is their own salon's roster. The
        write paths below are the ones that need rank.
        """
        await self._require_member(principal)
        return await self.repository.list_for_tenant(self.tenant_id, limit=limit, offset=offset)

    async def invite(
        self, principal: Principal, *, email: str, role: MembershipRole
    ) -> tuple[MembershipInvite, str]:
        """Starts staff access for `email`, redeemable only by whoever holds
        the returned token.

        Replaces granting straight to whichever account currently holds
        `email` (docs/14 TM-04): that account might not be who the inviter
        means, if someone else registered the address first — NOVA has no
        way to tell "the real new hire" from "whoever typed this email in
        first", and a token is what makes that distinction unnecessary.

        The token is returned once, here, and is not stored anywhere in
        plaintext — only `token_hash` is. Relaying it to the actual person is
        the inviter's job, through whatever channel they would use anyway.
        """
        await self._require_may_manage(principal, role)

        email = validate_email(email)
        token = secrets.token_urlsafe(32)
        invited_by = None if principal.kind is PrincipalKind.SERVICE else principal.subject_id

        record = MembershipInvite(
            tenant_id=self.tenant_id,
            email=email,
            role=role,
            token_hash=_hash_invite_token(token),
            invited_by=invited_by,
            expires_at=datetime.now(UTC) + self.INVITE_TTL,
        )
        self.invites.add(record)
        await self.repository.session.flush()
        return record, token

    async def accept_invite(
        self, principal: Principal, *, invite_id: UUID, token: str
    ) -> Membership:
        """Redeems an invite. The token is the entire credential.

        Deliberately does not check that `principal`'s email matches the
        invite's `email` — that field is the inviter's memo to themselves,
        never an authorization input, or this would be exactly the
        email-string trust TM-04 exists to remove. Whoever presents the
        correct token gets the membership, the same model as a Slack or
        GitHub invite link.

        This is the one route that reaches a tenant the caller is not yet
        authorized for — that is the whole point of accepting an invite — so
        it is not built on `get_tenant_context`. It opens the same narrow
        `bypass_tenant_scope` window `AuthService._issue_pair` already uses
        to read `memberships` before any tenant is known, closes it the
        moment the token has actually checked out, and only then writes.
        See the `SELF_AUTHORIZING_TENANT_ROUTES` comment in
        `tests/test_route_guards.py`.
        """
        if principal.kind is PrincipalKind.SERVICE:
            # Platform machinery already reaches every tenant; an invite is
            # for a person, and SERVICE has no `users` row to hold one.
            raise AuthorizationError("A service principal cannot accept an invite.")

        await bypass_tenant_scope(self.repository.session)
        record = await self.invites.get(invite_id)
        now = datetime.now(UTC)
        if (
            record is None
            or record.tenant_id != self.tenant_id
            or record.accepted_at is not None
            or record.expires_at < now
            or not hmac.compare_digest(_hash_invite_token(token), record.token_hash)
        ):
            raise InvalidInviteError()

        await set_tenant_scope(self.repository.session, self.tenant_id)

        membership_id = await self.repository.grant(
            user_id=principal.subject_id, tenant_id=self.tenant_id, role=MembershipRole(record.role)
        )
        if membership_id is None:
            raise DuplicateMembershipError(record.email)

        record.accepted_at = now
        record.accepted_by = principal.subject_id
        await self.repository.session.flush()
        return await self._load(membership_id)

    async def change_role(
        self, principal: Principal, *, membership_id: UUID, role: MembershipRole
    ) -> Membership:
        """Moves someone between roles.

        Authority is checked at both ends. Against the role they hold now, so a
        manager cannot demote an owner; and against the role they would move
        to, so a manager cannot promote a receptionist into a peer. Checking
        only the target would make every rank one step from owner.
        """
        membership = await self._load(membership_id)
        current = MembershipRole(membership.role)

        await self._require_may_manage(principal, current)
        await self._require_may_manage(principal, role)

        if current is MembershipRole.OWNER and role is not MembershipRole.OWNER:
            await self._guard_last_owner()

        membership.role = role
        await self.repository.session.flush()
        return membership

    async def revoke(self, principal: Principal, *, membership_id: UUID) -> Membership:
        """Takes access away, keeping the row.

        `is_active = False` rather than a DELETE: the unique constraint has no
        `is_active` predicate, so the row is also the slot the person comes
        back into if they are ever re-hired.

        Also bumps the person's `token_version`, which signs them out
        everywhere. Their tokens name this salon until they expire, and the
        version check on every request is what ends them now rather than up to
        15 minutes later. They sign in again to reach any other salon.
        """
        membership = await self._load(membership_id)
        current = MembershipRole(membership.role)

        await self._require_may_manage(principal, current)

        if current is MembershipRole.OWNER:
            await self._guard_last_owner()

        membership.is_active = False
        user = await self.users.session.get(User, membership.user_id)
        if user is not None:
            user.token_version += 1
        await self.repository.session.flush()
        return membership

    async def require_permission(self, principal: Principal, permission: StaffPermission) -> None:
        """Refuses a caller whose role in this tenant does not carry `permission`.

        A service principal is platform machinery and passes, as it does for
        `may_manage_role`. Anyone else is judged by their active membership row
        here, so a revoked member, or a staff token naming a salon its holder
        no longer works at, holds nothing.
        """
        is_service = principal.kind is PrincipalKind.SERVICE
        role = None if is_service else await self._actor_role(principal)
        if not role_allows(role, permission, actor_is_service=is_service):
            raise InsufficientRoleError(permission)

    # --- internals ---------------------------------------------------------

    async def _load(self, membership_id: UUID) -> Membership:
        membership = await self.repository.find_in_tenant(membership_id, self.tenant_id)
        if membership is None:
            raise MembershipNotFoundError(membership_id)
        return membership

    async def _actor_role(self, principal: Principal) -> MembershipRole | None:
        membership = await self.repository.find_for_user_and_tenant(
            principal.subject_id, self.tenant_id
        )
        return MembershipRole(membership.role) if membership is not None else None

    async def _require_member(self, principal: Principal) -> None:
        if principal.kind is PrincipalKind.SERVICE:
            return
        if await self._actor_role(principal) is None:
            raise AuthorizationError("You are not a member of this business.")

    async def _require_may_manage(self, principal: Principal, target: MembershipRole) -> None:
        is_service = principal.kind is PrincipalKind.SERVICE
        actor = None if is_service else await self._actor_role(principal)
        if not may_manage_role(actor, target, actor_is_service=is_service):
            raise AuthorizationError(f"Your role does not allow managing a '{target}'.")

    async def _guard_last_owner(self) -> None:
        if await self.repository.count_active_owners(self.tenant_id) <= 1:
            raise LastOwnerError()
