from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from app.db.repository import BaseRepository, TenantScopedRepository
from app.modules.identity.domain import MembershipRole
from app.modules.identity.models import Customer, Membership, MembershipInvite, Tenant, User


class TenantRepository(BaseRepository[Tenant]):
    """Tenant is the isolation root itself, so it extends the unscoped base.

    Every *other* module's repository must extend `TenantScopedRepository`.
    """

    model = Tenant

    async def get_by_slug(self, slug: str) -> Tenant | None:
        stmt = self._base_select().where(Tenant.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_ids(
        self, tenant_ids: frozenset[UUID], *, limit: int = 20, offset: int = 0
    ) -> list[Tenant]:
        """Only the tenants a principal actually belongs to.

        The unfiltered `list()` is still inherited but must not be reachable
        from an endpoint: it used to back `GET /tenants`, which meant anyone
        could enumerate every business on the platform along with its phone
        number.
        """
        if not tenant_ids:
            return []
        stmt = (
            self._base_select()
            .where(Tenant.id.in_(tuple(tenant_ids)))
            .order_by(Tenant.created_at)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class UserRepository(BaseRepository[User]):
    """Sign-in accounts. Not tenant-owned — one account, many salons."""

    model = User

    async def find_by_email(self, email: str) -> User | None:
        stmt = select(User).where(func.lower(User.email) == email.strip().lower())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class MembershipRepository(BaseRepository[Membership]):
    """Unscoped by necessity: this table is what *defines* a tenant scope.

    Unscoped in the *application* sense only. `memberships` carries the RLS
    policy from `d4e5f6a7b8c9`, so the rows this class can see are still
    whatever `app.current_tenant_id` allows — every method here takes an
    explicit `tenant_id` so the SQL says what it means rather than leaning on
    the connection setting, and the two agree on the request path because
    `get_tenant_context` set the scope from the same path value.

    The one caller that legitimately crosses tenants is token issue, which asks
    "which salons does this person belong to?" before any tenant is known. It
    opens the bypass explicitly; see `AuthService._issue_pair`.
    """

    model = Membership

    async def find_for_user_and_tenant(self, user_id: UUID, tenant_id: UUID) -> Membership | None:
        """The caller's own standing in one salon — the per-tenant role check.

        Read from the table rather than from `Principal.roles`, which flattens
        every membership a user holds across all tenants into one unkeyed set.
        """
        stmt = select(Membership).where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id,
            Membership.is_active.is_(True),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[Membership]:
        stmt = select(Membership).where(
            Membership.user_id == user_id, Membership.is_active.is_(True)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_in_tenant(self, membership_id: UUID, tenant_id: UUID) -> Membership | None:
        """One active membership, with its account loaded.

        Revoked rows are invisible here on purpose: a revoked membership is
        history, and the way back is a fresh grant, not a PATCH on a dead id.

        `populate_existing` because `grant()` writes through Core, which the
        unit of work does not see: without it a reinstated row already in the
        identity map would be read back at its pre-grant role.
        """
        stmt = (
            select(Membership)
            .where(
                Membership.id == membership_id,
                Membership.tenant_id == tenant_id,
                Membership.is_active.is_(True),
            )
            .options(selectinload(Membership.user))
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_tenant(
        self, tenant_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> list[Membership]:
        """This salon's staff list, oldest first so the owner heads it."""
        stmt = (
            select(Membership)
            .where(Membership.tenant_id == tenant_id, Membership.is_active.is_(True))
            .options(selectinload(Membership.user))
            .order_by(Membership.created_at)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_active_owners(self, tenant_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.tenant_id == tenant_id,
                Membership.role == MembershipRole.OWNER,
                Membership.is_active.is_(True),
            )
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def grant(self, *, user_id: UUID, tenant_id: UUID, role: MembershipRole) -> UUID | None:
        """Adds or reinstates a membership in one statement.

        `uq_memberships_user_tenant` has no `is_active` predicate, so there is
        exactly one row per (user, tenant) for the lifetime of the pair. A
        revoked membership is that row with `is_active = false`, and bringing
        the person back means flipping it — a second INSERT is an
        `IntegrityError`. Read-then-write would be correct until two owners
        add the same person at once, so it is an upsert instead.

        `WHERE is_active = false` on the conflict branch is what makes a grant
        to somebody who already works here return nothing rather than quietly
        rewriting their role; the service turns that into a 409 pointing at
        PATCH. `updated_at` is set by hand because `onupdate` does not reach
        into an ON CONFLICT SET clause.

        Returns the membership id, or None when the membership was already
        active.
        """
        stmt = (
            pg_insert(Membership)
            .values(user_id=user_id, tenant_id=tenant_id, role=role, is_active=True)
            .on_conflict_do_update(
                constraint="uq_memberships_user_tenant",
                set_={"role": role, "is_active": True, "updated_at": func.now()},
                where=Membership.is_active.is_(False),
            )
            .returning(Membership.id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class MembershipInviteRepository(TenantScopedRepository[MembershipInvite]):
    """Pending staff-access offers, redeemable by token (docs/14 TM-04).

    Tenant-scoped like every other `TenantOwnedMixin` table; `get` and `add`
    come from the base class unchanged.
    """

    model = MembershipInvite

    async def list_pending(
        self, tenant_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> list[MembershipInvite]:
        """Invites this tenant sent that nobody has redeemed yet.

        Never includes the token itself — that was shown once, at creation,
        and is not stored anywhere in plaintext to show again.
        """
        stmt = (
            select(MembershipInvite)
            .where(
                MembershipInvite.tenant_id == tenant_id,
                MembershipInvite.accepted_at.is_(None),
            )
            .order_by(MembershipInvite.created_at)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class CustomerRepository(TenantScopedRepository[Customer]):
    model = Customer

    def _active(self, stmt: Select) -> Select:
        return stmt.where(Customer.is_deleted.is_(False))

    async def get(self, id: UUID, *, include_deleted: bool = False) -> Customer | None:
        stmt = self._scope(self._base_select().where(Customer.id == id))
        if not include_deleted:
            stmt = self._active(stmt)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> Customer | None:
        stmt = self._active(self._scope(self._base_select().where(Customer.phone == phone)))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_unclaimed_by_phone(self, phone: str) -> Customer | None:
        """The record with this phone that no account has claimed yet, if any.

        Distinct from `get_by_phone`, which finds one regardless of who (if
        anyone) already owns it — that is exactly what let an unverified
        phone claim to be somebody else's already-linked customer (docs/14
        TM-01). `ensure_for_user` calls this one for the auto-claim branch.
        """
        stmt = self._active(
            self._scope(
                self._base_select().where(Customer.phone == phone, Customer.user_id.is_(None))
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: UUID) -> Customer | None:
        """The customer record this signed-in account owns within this tenant."""
        stmt = self._active(self._scope(self._base_select().where(Customer.user_id == user_id)))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(self, term: str, *, limit: int = 20, offset: int = 0) -> list[Customer]:
        """Reception lookup by partial name or phone."""
        pattern = f"%{term.strip().lower()}%"
        stmt = (
            self._active(
                self._scope(
                    self._base_select().where(
                        Customer.phone.ilike(pattern) | Customer.full_name.ilike(pattern)
                    )
                )
            )
            .order_by(Customer.full_name)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list(
        self, *, limit: int = 20, offset: int = 0, include_deleted: bool = False
    ) -> list[Customer]:
        stmt = self._scope(self._base_select())
        if not include_deleted:
            stmt = self._active(stmt)
        stmt = stmt.order_by(Customer.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
