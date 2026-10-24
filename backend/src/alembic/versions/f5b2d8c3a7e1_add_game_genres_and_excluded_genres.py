"""add game genres/categories and excluded_genres setting

Adds games.genres and games.categories (Steam genre and category
descriptions from appdetails) and settings.excluded_genres (genre names
auto-join skips, matched case-insensitively).

The game columns have no default on purpose: rows cached before this
revision keep SQL NULL, which means "not fetched yet". Game.needs_refresh and
GameRepository.get_stale_games both treat genres IS NULL as stale, so the
normal refresh paths backfill them from Steam; a fetched app with no genres
stores [] instead. Existing settings rows get excluded_genres '[]'.

Revision ID: f5b2d8c3a7e1
Revises: e3a9c7b5d1f4
Create Date: 2026-10-24

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f5b2d8c3a7e1"
down_revision: str | Sequence[str] | None = "e3a9c7b5d1f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("games", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "genres",
                sa.JSON(),
                nullable=True,
                comment="Steam genre names (None = not fetched yet, [] = none)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "categories",
                sa.JSON(),
                nullable=True,
                comment="Steam category names (None = not fetched yet, [] = none)",
            )
        )

    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "excluded_genres",
                sa.JSON(),
                nullable=False,
                server_default="[]",
                comment="Genre names auto-join skips (case-insensitive)",
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.drop_column("excluded_genres")

    with op.batch_alter_table("games", schema=None) as batch_op:
        batch_op.drop_column("categories")
        batch_op.drop_column("genres")
