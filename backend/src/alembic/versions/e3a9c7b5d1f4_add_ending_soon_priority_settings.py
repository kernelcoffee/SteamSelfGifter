"""add ending-soon priority settings

Adds ending_soon_priority_enabled and ending_soon_threshold_minutes: when the
toggle is on, eligible giveaways whose end_time is within the threshold are
entered after wishlist and DLC ones but before the rest, soonest first. The
lift only changes entry order, never eligibility. Existing rows get the
defaults (off, 60 minutes).

Revision ID: e3a9c7b5d1f4
Revises: a7d4e8f2c6b1
Create Date: 2026-10-24

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3a9c7b5d1f4"
down_revision: str | Sequence[str] | None = "a7d4e8f2c6b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "ending_soon_priority_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
                comment="Giveaways ending within the threshold are entered after wishlist and DLC ones, soonest first",
            )
        )
        batch_op.add_column(
            sa.Column(
                "ending_soon_threshold_minutes",
                sa.Integer(),
                nullable=False,
                server_default="60",
                comment="Minutes before end_time within which a giveaway counts as ending soon (5-10080)",
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.drop_column("ending_soon_threshold_minutes")
        batch_op.drop_column("ending_soon_priority_enabled")
