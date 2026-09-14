"""make notifications.scheduled_for non-nullable, and retire the undelivered backlog

`scheduled_for` was nullable and written *only* by the quiet-hours branch of
`NotificationService.enqueue`, while the delivery job filtered
`scheduled_for IS NOT NULL`. Every transactional notification — every booking
confirmation, queue call and payment receipt — was therefore stored with NULL
and never picked up. The column now means one thing, "not before this time",
and is always set.

Three steps, and the middle one is the reason this migration is hand-written.

**The stale sweep.** Fixing the predicate without it would make the first
delivery tick after deploy send the entire backlog: "your booking is confirmed"
for appointments that happened months ago, "you're next in the queue" to people
who were served and went home. That is worse for a salon than never having sent
anything. Anything still PENDING and older than a day has missed its moment, so
it is retired here instead.

SUPPRESSED rather than FAILED, matching how the notification module already
uses the two: nothing went wrong technically, we simply chose not to send. It
also keeps FAILED meaning "delivery error" for alerting. The `error` string
names this revision so the rows stay explicable later.

Anything younger than a day is left PENDING and *will* be delivered on the
first tick — a confirmation from this morning is still worth sending, and that
is the behaviour the fix exists to restore.

> [!warning] Deliberately irreversible
> `downgrade()` restores nullability but cannot un-suppress. The status of the
> swept rows is recoverable only from a backup. This is accepted: replaying a
> months-old backlog at a live salon is the worse outcome.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Older than this and a transactional message has missed the event it
#: describes. A day is generous on purpose — it covers an overnight outage
#: without replaying anything a customer would find baffling.
_STALE_AFTER = "24 hours"


def upgrade() -> None:
    # 1. Retire the backlog that has been accumulating undelivered, BEFORE the
    #    delivery job can ever see it.
    op.execute(
        sa.text(
            """
            UPDATE notifications
               SET status = 'suppressed',
                   error  = 'stale_undelivered_pre_c9d0e1f2a3b4'
             WHERE status = 'pending'
               AND created_at < now() - interval '""" + _STALE_AFTER + """'
            """
        )
    )

    # 2. Backfill every remaining NULL. `created_at` is the honest answer: it is
    #    when the message became ready to send, which is exactly what the column
    #    now means. Applies to swept rows too — they still need a value.
    op.execute(
        sa.text(
            """
            UPDATE notifications
               SET scheduled_for = created_at
             WHERE scheduled_for IS NULL
            """
        )
    )

    # 3. One meaning, enforced.
    op.alter_column(
        "notifications",
        "scheduled_for",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )


def downgrade() -> None:
    # Nullability only. The swept rows stay SUPPRESSED — see the module
    # docstring; restoring them would require knowing which were suppressed by
    # this migration rather than by a genuine consent refusal, and the `error`
    # marker is evidence rather than a safe rollback key.
    op.alter_column(
        "notifications",
        "scheduled_for",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
