"""add wishlist priority toggle to settings

Adds wishlist_priority_enabled: when on (default), wishlist giveaways bypass
the autojoin quality filters and are entered before everything else.

Revision ID: c8d2e5f1a3b9
Revises: b1f4c0a9d2e7
Create Date: 2026-07-18 14:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c8d2e5f1a3b9'
down_revision: str | Sequence[str] | None = 'b1f4c0a9d2e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'wishlist_priority_enabled',
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
                comment='Wishlist giveaways bypass autojoin filters and are entered first',
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.drop_column('wishlist_priority_enabled')
