"""add entries count to giveaways

The scraper has always parsed the entry count from listing pages; store it so
the UI can show and filter by chance-to-win (copies / entries).

Revision ID: d4e7f2a8b1c5
Revises: c8d2e5f1a3b9
Create Date: 2026-07-18 17:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e7f2a8b1c5'
down_revision: str | Sequence[str] | None = 'c8d2e5f1a3b9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('giveaways', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'entries',
                sa.Integer(),
                nullable=False,
                server_default='0',
                comment='Entry count as of the last scan (0 = none yet or unknown)',
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('giveaways', schema=None) as batch_op:
        batch_op.drop_column('entries')
