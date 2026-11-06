"""Sara, the call-center agent: phone lines, calls, and voice consent (ADR-0017).

Revision ID: 9c8d7e6f5a4b
Revises: d2e3f4a5b6c7
Create Date: 2026-10-22 12:00:00.000000

Both new tables are tenant-owned, so each gets forced RLS and the
`tenant_isolation` policy, as `e5f6a7b8c9d0` gives every tenant table.
Default privileges grant `nova_app` DML on them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c8d7e6f5a4b"
down_revision: str | Sequence[str] | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_TABLES = ("phone_lines", "voice_calls")


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
    """Create phone_lines and voice_calls under RLS; add voice consent to customers."""
    op.create_table(
        "phone_lines",
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("number_e164", sa.String(length=20), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_phone_lines_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_phone_lines")),
        sa.UniqueConstraint("number_e164", name=op.f("uq_phone_lines_number_e164")),
    )
    op.create_index(op.f("ix_phone_lines_business_id"), "phone_lines", ["business_id"])
    op.create_index(op.f("ix_phone_lines_tenant_id"), "phone_lines", ["tenant_id"])

    op.create_table(
        "voice_calls",
        sa.Column("line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gateway_call_id", sa.String(length=128), nullable=True),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("caller_e164", sa.String(length=32), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("turns", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("code_hash", sa.String(length=64), nullable=True),
        sa.Column("code_attempts", sa.Integer(), nullable=False),
        sa.Column("code_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pending_cancellation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reminder_answered", sa.Boolean(), nullable=False),
        sa.Column("last_answer_key", sa.String(length=64), nullable=True),
        sa.Column("last_reply", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["line_id"],
            ["phone_lines.id"],
            name=op.f("fk_voice_calls_line_id_phone_lines"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_voice_calls_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_voice_calls")),
        sa.UniqueConstraint("tenant_id", "gateway_call_id", name=op.f("uq_voice_calls_tenant_id")),
    )
    op.create_index(op.f("ix_voice_calls_tenant_id"), "voice_calls", ["tenant_id"])
    op.create_index(
        "uq_voice_calls_reminder_booking",
        "voice_calls",
        ["booking_id"],
        unique=True,
        postgresql_where=sa.text("purpose = 'reminder'"),
    )

    op.add_column(
        "customers",
        sa.Column("voice_consent", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("customers", sa.Column("voice_consent_source", sa.String(16), nullable=True))
    op.add_column(
        "customers", sa.Column("voice_consent_by", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "customers", sa.Column("voice_consent_at", sa.DateTime(timezone=True), nullable=True)
    )

    for table in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
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
    """Drop the call-center tables and the voice consent columns."""
    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_column("customers", "voice_consent_at")
    op.drop_column("customers", "voice_consent_by")
    op.drop_column("customers", "voice_consent_source")
    op.drop_column("customers", "voice_consent")
    op.drop_index("uq_voice_calls_reminder_booking", table_name="voice_calls")
    op.drop_index(op.f("ix_voice_calls_tenant_id"), table_name="voice_calls")
    op.drop_table("voice_calls")
    op.drop_index(op.f("ix_phone_lines_tenant_id"), table_name="phone_lines")
    op.drop_index(op.f("ix_phone_lines_business_id"), table_name="phone_lines")
    op.drop_table("phone_lines")
