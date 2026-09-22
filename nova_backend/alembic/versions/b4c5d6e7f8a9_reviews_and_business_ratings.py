"""reviews and business ratings

Adds verified ratings (the `review` module):

1. `reviews` — one customer's 1-5 rating of one completed booking, with an
   optional staff-only comment. Tenant-owned, so it gets the ordinary forced
   `tenant_isolation` policy (autogenerate does not emit RLS) and no discovery
   policy: the public marketplace never reads this table.

2. `businesses.rating_count` / `rating_sum` — running totals the marketplace
   ranks and displays by. They live on `businesses` because discovery already
   reads that table through its SELECT-only window; putting the totals there
   avoids opening a second cross-tenant window onto `reviews`. The check
   constraints keep the totals consistent with "every rating is 1-5".

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-09-22

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: str | Sequence[str] | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "businesses",
        sa.Column("rating_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "businesses",
        sa.Column("rating_sum", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_check_constraint("rating_count_non_negative", "businesses", "rating_count >= 0")
    op.create_check_constraint(
        "rating_sum_in_range",
        "businesses",
        "rating_sum BETWEEN rating_count AND rating_count * 5",
    )

    op.create_table(
        "reviews",
        sa.Column("booking_id", sa.UUID(), nullable=False),
        sa.Column("business_id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name=op.f("ck_reviews_rating_range")),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["bookings.id"],
            name=op.f("fk_reviews_booking_id_bookings"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_reviews_business_id_businesses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_reviews_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_reviews_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reviews")),
    )
    op.create_index(
        "ix_reviews_tenant_business_created",
        "reviews",
        ["tenant_id", "business_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_reviews_tenant_customer", "reviews", ["tenant_id", "customer_id"], unique=False
    )
    op.create_index(op.f("ix_reviews_tenant_id"), "reviews", ["tenant_id"], unique=False)
    op.create_index("uq_reviews_booking_id", "reviews", ["booking_id"], unique=True)

    op.execute("ALTER TABLE reviews ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE reviews FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON reviews
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
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON reviews")
    op.drop_index("uq_reviews_booking_id", table_name="reviews")
    op.drop_index(op.f("ix_reviews_tenant_id"), table_name="reviews")
    op.drop_index("ix_reviews_tenant_customer", table_name="reviews")
    op.drop_index("ix_reviews_tenant_business_created", table_name="reviews")
    op.drop_table("reviews")
    op.drop_constraint(op.f("ck_businesses_rating_sum_in_range"), "businesses", type_="check")
    op.drop_constraint(op.f("ck_businesses_rating_count_non_negative"), "businesses", type_="check")
    op.drop_column("businesses", "rating_sum")
    op.drop_column("businesses", "rating_count")
