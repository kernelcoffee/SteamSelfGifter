"""Add settings.log_retention_days for activity-log pruning

Activity logs previously grew forever (only manual Clear All). The
automation cycle now prunes rows older than this many days; 0 disables
pruning.

Revision ID: a7d4e8f2c6b1
Revises: f1b8c5d3a9e2
Create Date: 2026-07-21

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7d4e8f2c6b1"
down_revision: str | Sequence[str] | None = "f1b8c5d3a9e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "log_retention_days",
                sa.Integer(),
                nullable=False,
                server_default="30",
                comment="Activity logs older than this many days are pruned (0 = keep forever)",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.drop_column("log_retention_days")
