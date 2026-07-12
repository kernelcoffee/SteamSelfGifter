"""add giveaway eligibility diagnostics

Adds eligibility_reason and eligibility_checked_at to the giveaways table so the
autojoin decision (and its reason) is recorded per giveaway.

Revision ID: b1f4c0a9d2e7
Revises: 93fe35470006
Create Date: 2026-06-17 15:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b1f4c0a9d2e7'
down_revision: str | Sequence[str] | None = '93fe35470006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('giveaways', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'eligibility_reason',
                sa.String(),
                nullable=True,
                comment="Outcome of the last autojoin evaluation (e.g. 'eligible', "
                        "'score_below_min', 'no_game_data'); NULL = never evaluated",
            )
        )
        batch_op.add_column(
            sa.Column(
                'eligibility_checked_at',
                sa.DateTime(),
                nullable=True,
                comment='When eligibility_reason was last computed (UTC)',
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('giveaways', schema=None) as batch_op:
        batch_op.drop_column('eligibility_checked_at')
        batch_op.drop_column('eligibility_reason')
