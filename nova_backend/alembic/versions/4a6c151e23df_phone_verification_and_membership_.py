"""phone verification and membership invites

Two independent fixes from the 2026-09-15 threat model, both about trusting an
unverified contact channel to decide who someone is:

  - TM-01: `CustomerService.ensure_for_user` claimed an existing, unclaimed
    customer record by phone match alone, so registering with someone else's
    number read their booking history and, on any committing self-service
    path, permanently took over their identity at that salon.
    `users.phone_verified_at` gates that claim on proof of the number, set
    only once a short-lived, purpose-signed JWT sent over WhatsApp
    (`AuthService.request_phone_verification` / `confirm_phone_verification`,
    `security.issue_purpose_token` / `decode_purpose_token`) comes back
    verified. No table backs the token itself — the signature is the whole
    check, so there is nothing to store or invalidate.
  - TM-04: `MembershipService.grant` resolved the grantee by
    `users.find_by_email`, so whoever registered an address first — not
    necessarily who the inviter meant — received the membership.
    `membership_invites` replaces that: a random token is the only
    credential, checked against `token_hash`; the row's `email` is the
    inviter's own record of intent, never used to authorize acceptance.

Revision ID: 4a6c151e23df
Revises: f3c4d5e6a7b8
Create Date: 2026-09-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4a6c151e23df"
down_revision: str | Sequence[str] | None = "f3c4d5e6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column("users", sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True))

    # --- membership_invites: tenant-owned, so it needs the RLS policy -------

    op.create_table(
        "membership_invites",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("invited_by", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by", sa.UUID(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_membership_invites_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        # SET NULL, not CASCADE: deleting the inviter's or accepter's account
        # must not erase the tenant's own record of the invite.
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            name=op.f("fk_membership_invites_invited_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by"],
            ["users.id"],
            name=op.f("fk_membership_invites_accepted_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership_invites")),
    )
    op.create_index(op.f("ix_membership_invites_tenant_id"), "membership_invites", ["tenant_id"])
    op.create_index(
        "ix_membership_invites_tenant_pending",
        "membership_invites",
        ["tenant_id", "accepted_at"],
    )

    # Same policy as d4e5f6a7b8c9 / e5f6a7b8c9d0. A new tenant-owned table
    # gets this, or the database-level half of tenant isolation silently
    # stops covering it — see CLAUDE.md "Autogenerate does not emit RLS".
    op.execute("ALTER TABLE membership_invites ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE membership_invites FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON membership_invites
        USING (
            current_setting('app.bypass_rls', true) = 'on'
            OR tenant_id::text = current_setting('app.current_tenant_id', true)
        )
        WITH CHECK (
            current_setting('app.bypass_rls', true) = 'on'
            OR tenant_id::text = current_setting('app.current_tenant_id', true)
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON membership_invites")
    op.execute("ALTER TABLE membership_invites NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE membership_invites DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_membership_invites_tenant_pending", table_name="membership_invites")
    op.drop_index(op.f("ix_membership_invites_tenant_id"), table_name="membership_invites")
    op.drop_table("membership_invites")

    op.drop_column("users", "phone_verified_at")
