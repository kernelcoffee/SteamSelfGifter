"""Add giveaways.safety_checked_at for safety verdict freshness

Revision ID: f1b8c5d3a9e2
Revises: e9a3b6c4d2f7
Create Date: 2026-07-21

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1b8c5d3a9e2"
down_revision: str | Sequence[str] | None = "e9a3b6c4d2f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("giveaways") as batch_op:
        batch_op.add_column(
            sa.Column(
                "safety_checked_at",
                sa.DateTime(),
                nullable=True,
                comment="When the safety verdict was last computed (UTC); NULL = never checked",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("giveaways") as batch_op:
        batch_op.drop_column("safety_checked_at")
