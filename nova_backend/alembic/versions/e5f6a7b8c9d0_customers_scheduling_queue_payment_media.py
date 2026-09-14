"""customers, scheduling, queue, payment, media, notifications

Completes the schema for the remaining bounded contexts. Hand-written for the
same reason as the bookings migration: no database was reachable to
autogenerate against, and several constraints here (partial unique indexes, the
cross-tenant webhook index) do not autogenerate cleanly anyway. Verify with
`alembic check` once Postgres is up.

Tables added, and the docs section each is specified in:

    customers            docs/08 section 9
    provider_schedules   docs/03 section 2 (the `Schedule` aggregate)
    schedule_exceptions  — dated overrides of the weekly pattern
    slot_holds           docs/04 section 2A, docs/10 section 5
    queues               docs/08 section 11
    queue_entries        docs/08 section 12
    tickets              docs/08 section 13
    payments             docs/08 section 14
    payment_refunds      docs/07 section 8 (refunds are separate records)
    webhook_events       docs/08 section 17
    media_assets         docs/08 section 15
    notifications        — the notification context's delivery log

Plus `bookings.notes`, which docs/08 section 10 lists and the original table
omitted.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: New tables carrying tenant_id that need the RLS policy from d4e5f6a7b8c9.
#: `webhook_events` is deliberately absent — a webhook arrives before its tenant
#: is known, so the row must be insertable with no tenant scope set.
_TENANT_TABLES = (
    "customers",
    "provider_schedules",
    "schedule_exceptions",
    "slot_holds",
    "queues",
    "queue_entries",
    "tickets",
    "payments",
    "payment_refunds",
    "media_assets",
    "notifications",
)


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


def _tenant_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"],
        ["tenants.id"],
        name=op.f(f"fk_{table}_tenant_id_tenants"),
        ondelete="CASCADE",
    )


def upgrade() -> None:
    """Upgrade schema."""

    # --- identity: customers ---------------------------------------------

    op.create_table(
        "customers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("preferred_language", sa.String(length=8), nullable=False),
        sa.Column("marketing_consent", sa.Boolean(), nullable=False),
        sa.Column("whatsapp_consent", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        _tenant_fk("customers"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_customers_user_id_users"),
            # SET NULL, not CASCADE: deleting a login account must not erase
            # the salon's record of a customer who has appointment history.
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
    )
    op.create_index(op.f("ix_customers_tenant_id"), "customers", ["tenant_id"])
    op.create_index(op.f("ix_customers_is_deleted"), "customers", ["is_deleted"])
    op.create_index("ix_customers_tenant_user", "customers", ["tenant_id", "user_id"])
    # Phone is the identity key within a tenant (docs/08 section 9). Partial on
    # is_deleted so a retired record does not block re-registering the number.
    op.create_index(
        "uq_customers_tenant_phone",
        "customers",
        ["tenant_id", "phone"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )

    # --- booking: schedules, exceptions, holds, notes ---------------------

    op.add_column("bookings", sa.Column("notes", sa.Text(), nullable=True))

    op.create_table(
        "provider_schedules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_minute", sa.Integer(), nullable=False),
        sa.Column("end_minute", sa.Integer(), nullable=False),
        *_timestamps(),
        _tenant_fk("provider_schedules"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_schedules")),
        sa.UniqueConstraint(
            "tenant_id",
            "provider_id",
            "weekday",
            "start_minute",
            name=op.f("uq_provider_schedules_slot"),
        ),
        sa.CheckConstraint(
            "weekday BETWEEN 0 AND 6", name=op.f("ck_provider_schedules_weekday")
        ),
        sa.CheckConstraint(
            "start_minute >= 0 AND end_minute <= 1440 AND end_minute > start_minute",
            name=op.f("ck_provider_schedules_window"),
        ),
    )
    op.create_index(
        op.f("ix_provider_schedules_tenant_id"), "provider_schedules", ["tenant_id"]
    )
    op.create_index(
        "ix_provider_schedules_tenant_provider",
        "provider_schedules",
        ["tenant_id", "provider_id"],
    )

    op.create_table(
        "schedule_exceptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("on_date", sa.Date(), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        sa.Column("start_minute", sa.Integer(), nullable=True),
        sa.Column("end_minute", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        *_timestamps(),
        _tenant_fk("schedule_exceptions"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schedule_exceptions")),
        sa.CheckConstraint(
            "is_closed OR (start_minute IS NOT NULL AND end_minute IS NOT NULL "
            "AND end_minute > start_minute)",
            name=op.f("ck_schedule_exceptions_window"),
        ),
    )
    op.create_index(
        op.f("ix_schedule_exceptions_tenant_id"), "schedule_exceptions", ["tenant_id"]
    )
    op.create_index(
        "ix_schedule_exceptions_tenant_provider_date",
        "schedule_exceptions",
        ["tenant_id", "provider_id", "on_date"],
    )

    op.create_table(
        "slot_holds",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hold_token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        _tenant_fk("slot_holds"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_slot_holds")),
        sa.UniqueConstraint("hold_token", name=op.f("uq_slot_holds_token")),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_slot_holds_end_after_start")),
    )
    op.create_index(op.f("ix_slot_holds_tenant_id"), "slot_holds", ["tenant_id"])
    op.create_index(
        "ix_slot_holds_tenant_provider_window",
        "slot_holds",
        ["tenant_id", "provider_id", "starts_at"],
    )
    op.create_index("ix_slot_holds_expiry", "slot_holds", ["expires_at"])

    # --- queue ------------------------------------------------------------

    op.create_table(
        "queues",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=False),
        sa.Column("name_en", sa.String(length=255), nullable=False),
        sa.Column("name_ar", sa.String(length=255), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False),
        sa.Column("average_service_minutes", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        _tenant_fk("queues"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_queues")),
        sa.UniqueConstraint(
            "tenant_id", "location_id", "name_en", name=op.f("uq_queues_tenant_loc_name")
        ),
    )
    op.create_index(op.f("ix_queues_tenant_id"), "queues", ["tenant_id"])
    op.create_index(op.f("ix_queues_is_deleted"), "queues", ["is_deleted"])
    op.create_index("ix_queues_tenant_location", "queues", ["tenant_id", "location_id"])

    op.create_table(
        "queue_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("queue_id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=True),
        sa.Column("booking_id", sa.UUID(), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("party_size", sa.Integer(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("called_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        _tenant_fk("queue_entries"),
        sa.ForeignKeyConstraint(
            ["queue_id"],
            ["queues.id"],
            name=op.f("fk_queue_entries_queue_id_queues"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_queue_entries")),
        # Position is monotonic per queue and never reused, so this both
        # enforces that and turns a lost race for the next position into a
        # retryable 409 rather than two customers sharing a place.
        sa.UniqueConstraint(
            "queue_id", "position", name=op.f("uq_queue_entries_queue_position")
        ),
        sa.CheckConstraint(
            "party_size BETWEEN 1 AND 20", name=op.f("ck_queue_entries_party_size")
        ),
    )
    op.create_index(op.f("ix_queue_entries_tenant_id"), "queue_entries", ["tenant_id"])
    op.create_index(op.f("ix_queue_entries_status"), "queue_entries", ["status"])
    op.create_index(
        "ix_queue_entries_tenant_queue_status_position",
        "queue_entries",
        ["tenant_id", "queue_id", "status", "position"],
    )
    op.create_index(
        "ix_queue_entries_tenant_customer", "queue_entries", ["tenant_id", "customer_id"]
    )

    op.create_table(
        "tickets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("booking_id", sa.UUID(), nullable=True),
        sa.Column("queue_entry_id", sa.UUID(), nullable=True),
        sa.Column("ticket_code", sa.String(length=100), nullable=False),
        # A HASH of the QR token, never the token (docs/08 section 1). Reading
        # this table must not let anyone check in as somebody else.
        sa.Column("qr_token_hash", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        _tenant_fk("tickets"),
        sa.ForeignKeyConstraint(
            ["queue_entry_id"],
            ["queue_entries.id"],
            name=op.f("fk_tickets_queue_entry_id_queue_entries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
        sa.UniqueConstraint("ticket_code", name=op.f("uq_tickets_code")),
        sa.CheckConstraint(
            "booking_id IS NOT NULL OR queue_entry_id IS NOT NULL",
            name=op.f("ck_tickets_has_subject"),
        ),
    )
    op.create_index(op.f("ix_tickets_tenant_id"), "tickets", ["tenant_id"])
    op.create_index("ix_tickets_tenant_status", "tickets", ["tenant_id", "status"])
    op.create_index("ix_tickets_tenant_booking", "tickets", ["tenant_id", "booking_id"])
    op.create_index(
        "ix_tickets_tenant_queue_entry", "tickets", ["tenant_id", "queue_entry_id"]
    )

    # --- payment ----------------------------------------------------------

    op.create_table(
        "payments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("booking_id", sa.UUID(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("refunded_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("gateway", sa.String(length=50), nullable=False),
        sa.Column("gateway_payment_id", sa.String(length=255), nullable=True),
        sa.Column("webhook_verified", sa.Boolean(), nullable=False),
        sa.Column("failure_code", sa.String(length=255), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        _tenant_fk("payments"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.CheckConstraint("amount >= 0", name=op.f("ck_payments_amount_non_negative")),
        sa.CheckConstraint(
            "refunded_amount >= 0 AND refunded_amount <= amount",
            name=op.f("ck_payments_refund_within_amount"),
        ),
    )
    op.create_index(op.f("ix_payments_tenant_id"), "payments", ["tenant_id"])
    op.create_index("ix_payments_tenant_booking", "payments", ["tenant_id", "booking_id"])
    op.create_index("ix_payments_tenant_status", "payments", ["tenant_id", "status"])
    # Global, not tenant-scoped: the webhook handler arrives knowing only the
    # gateway's id and must resolve the tenant from it. Two payments sharing
    # one gateway id would make that ambiguous, and ambiguity here credits the
    # wrong booking.
    op.create_index(
        "uq_payments_gateway_payment_id",
        "payments",
        ["gateway_payment_id"],
        unique=True,
        postgresql_where=sa.text("gateway_payment_id IS NOT NULL"),
    )

    op.create_table(
        "payment_refunds",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("payment_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("gateway_refund_id", sa.String(length=255), nullable=True),
        *_timestamps(),
        _tenant_fk("payment_refunds"),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name=op.f("fk_payment_refunds_payment_id_payments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_refunds")),
        sa.UniqueConstraint("gateway_refund_id", name=op.f("uq_payment_refunds_gateway_id")),
        sa.CheckConstraint("amount > 0", name=op.f("ck_payment_refunds_amount_positive")),
    )
    op.create_index(op.f("ix_payment_refunds_tenant_id"), "payment_refunds", ["tenant_id"])
    op.create_index(
        "ix_payment_refunds_tenant_payment", "payment_refunds", ["tenant_id", "payment_id"]
    )

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=True),
        # Nullable and NOT tenant-owned: a webhook arrives before we know whose
        # it is, and it must be insertable with no tenant scope set.
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("signature_verified", sa.Boolean(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_events")),
    )
    # THE dedupe mechanism (docs/08 section 17). Moyasar retries, and without
    # this a redelivered capture would double-confirm a booking.
    op.create_index(
        "ix_webhook_provider_external_id",
        "webhook_events",
        ["provider", "external_event_id"],
        unique=True,
    )
    op.create_index("ix_webhook_events_unprocessed", "webhook_events", ["processed_at"])

    # --- media ------------------------------------------------------------

    op.create_table(
        "media_assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("business_id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        # A path, never bytes. docs/09 #13.
        sa.Column("webdav_path", sa.String(length=1000), nullable=False),
        sa.Column("thumbnail_path", sa.String(length=1000), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("is_ready", sa.Boolean(), nullable=False),
        sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        _tenant_fk("media_assets"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_assets")),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_media_assets_size_positive")),
    )
    op.create_index(op.f("ix_media_assets_tenant_id"), "media_assets", ["tenant_id"])
    op.create_index(op.f("ix_media_assets_is_deleted"), "media_assets", ["is_deleted"])
    op.create_index(
        "ix_media_assets_tenant_business", "media_assets", ["tenant_id", "business_id"]
    )
    op.create_index("ix_media_assets_tenant_kind", "media_assets", ["tenant_id", "kind"])

    # --- notification -----------------------------------------------------

    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("template", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        _tenant_fk("notifications"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        # The idempotency key for delivery. The outbox is at-least-once, so the
        # same BookingConfirmed can arrive twice; this is what stops the
        # customer receiving two identical messages.
        sa.UniqueConstraint(
            "tenant_id", "dedupe_key", name=op.f("uq_notifications_tenant_dedupe")
        ),
    )
    op.create_index(op.f("ix_notifications_tenant_id"), "notifications", ["tenant_id"])
    op.create_index(
        "ix_notifications_tenant_customer", "notifications", ["tenant_id", "customer_id"]
    )
    op.create_index(
        "ix_notifications_tenant_status", "notifications", ["tenant_id", "status"]
    )
    op.create_index(
        "ix_notifications_scheduled", "notifications", ["status", "scheduled_for"]
    )

    # --- row-level security ------------------------------------------------
    #
    # Same policy as d4e5f6a7b8c9. Every new tenant-owned table gets it, or the
    # database-level half of tenant isolation silently stops covering the
    # majority of the schema.

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
    """Downgrade schema."""
    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("notifications")
    op.drop_table("media_assets")
    op.drop_table("webhook_events")
    op.drop_table("payment_refunds")
    op.drop_table("payments")
    op.drop_table("tickets")
    op.drop_table("queue_entries")
    op.drop_table("queues")
    op.drop_table("slot_holds")
    op.drop_table("schedule_exceptions")
    op.drop_table("provider_schedules")
    op.drop_column("bookings", "notes")
    op.drop_table("customers")
