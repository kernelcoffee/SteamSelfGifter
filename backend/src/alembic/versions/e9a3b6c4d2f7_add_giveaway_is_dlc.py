"""add is_dlc flag and dlc_priority_enabled setting

DLC listings on SteamGifts are for games the user owns, so DLC giveaways get
the same autojoin priority treatment as wishlist ones. The is_dlc flag records
which giveaways came from a DLC scan (now part of every scan, like wishlist);
dlc_priority_enabled replaces dlc_enabled and only controls the autojoin
priority/bypass, not the scanning.

Revision ID: e9a3b6c4d2f7
Revises: d4e7f2a8b1c5
Create Date: 2026-07-19 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e9a3b6c4d2f7'
down_revision: str | Sequence[str] | None = 'd4e7f2a8b1c5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('giveaways', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'is_dlc',
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
                comment='DLC giveaway (DLC listings are for games the user owns)',
            )
        )

    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'dlc_priority_enabled',
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
                comment='DLC giveaways bypass autojoin filters and are entered '
                        'after wishlist ones',
            )
        )

    # Carry the old opt-in over: users who entered DLC giveaways before keep
    # entering them (now with priority) instead of being silently reset.
    op.execute('UPDATE settings SET dlc_priority_enabled = dlc_enabled')

    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.drop_column('dlc_enabled')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'dlc_enabled',
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
                comment='Whether to enter DLC giveaways',
            )
        )

    op.execute('UPDATE settings SET dlc_enabled = dlc_priority_enabled')

    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.drop_column('dlc_priority_enabled')

    with op.batch_alter_table('giveaways', schema=None) as batch_op:
        batch_op.drop_column('is_dlc')
