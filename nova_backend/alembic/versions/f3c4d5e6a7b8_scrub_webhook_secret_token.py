"""remove the webhook shared secret from stored webhook payloads

SEC-07 of the 2026-09-15 security audit. When Moyasar authenticates a webhook
with a `secret_token` in its body, the whole body was stored in
`webhook_events.payload`, so the secret that authenticates every webhook sat in
a table with no row-level security. Anyone able to read it could sign a "paid"
event. The processor now drops the field before storing; this removes it from
the rows already there.

Rotate the secret in the Moyasar dashboard wherever such a row existed: deleting
a copy does not un-leak it.

Irreversible on purpose: `downgrade` cannot put a secret back, and should not.

Revision ID: f3c4d5e6a7b8
Revises: f2b3c4d5e6a7
Create Date: 2026-09-15

"""

from collections.abc import Sequence

from alembic import op

revision: str = "f3c4d5e6a7b8"
down_revision: str | Sequence[str] | None = "f2b3c4d5e6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "UPDATE webhook_events SET payload = payload - 'secret_token' "
        "WHERE payload -> 'secret_token' IS NOT NULL"
    )


def downgrade() -> None:
    """Nothing to undo: a removed secret stays removed."""
