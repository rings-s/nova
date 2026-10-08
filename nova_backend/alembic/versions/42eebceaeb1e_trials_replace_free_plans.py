"""Every plan starts with a free week: no plan is free any more.

Solo used to cost nothing, so a business on it never paid. It now costs 400 SAR
a month, and the monthly close bills each subscription its plan's price; left
as they were, these businesses would be charged for a plan they took for free.
Instead each gets the free week every new subscription now starts with
(`TRIAL_DAYS`), counted from this migration, and is locked if it does not pay.

A business that never chose a plan is taken off the marketplace until it
does; choosing one starts its trial and puts the listing back up.

`trial_ai_messages_used` counts AI messages against the trial's allowance.

Revision ID: 42eebceaeb1e
Revises: b2e3f4a5c6d7
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "42eebceaeb1e"
down_revision: str | None = "b2e3f4a5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: `billing.domain.TRIAL_DAYS` when this was written; a migration must not
#: change meaning if that constant later does.
_TRIAL_DAYS = 7


def _bypass_rls() -> None:
    """Tenant tables force RLS even on their owner, and no tenant is set here."""
    op.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "subscriptions",
        sa.Column("trial_ai_messages_used", sa.Integer(), server_default="0", nullable=False),
    )
    _bypass_rls()
    op.execute(
        "UPDATE subscriptions SET status = 'trialing', "
        f"trial_ends_at = CURRENT_DATE + {_TRIAL_DAYS} "
        "WHERE tier = 'solo' AND status = 'active'"
    )
    op.execute(
        f"UPDATE subscriptions SET trial_ends_at = CURRENT_DATE + {_TRIAL_DAYS} "
        "WHERE status = 'trialing' AND trial_ends_at IS NULL"
    )
    op.execute(
        "UPDATE businesses SET hidden_by_billing = true "
        "WHERE NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.business_id = businesses.id)"
    )


def downgrade() -> None:
    """Downgrade schema: Solo was free, and a business needed no plan to be listed."""
    _bypass_rls()
    op.execute(
        "UPDATE businesses SET hidden_by_billing = false "
        "WHERE NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.business_id = businesses.id)"
    )
    op.execute(
        "UPDATE subscriptions SET status = 'active', trial_ends_at = NULL "
        "WHERE tier = 'solo' AND status IN ('trialing', 'pending_payment')"
    )
    op.drop_column("subscriptions", "trial_ai_messages_used")
