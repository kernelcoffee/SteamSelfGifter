"""auto-join priority list, included genres and eligibility detail

Moves the auto-join settings to the one-registry decision engine
(services/eligibility.py). Upgrade, in order:

a. settings.included_genres (JSON NOT NULL, default '[]', after
   excluded_genres): genre names of which auto-join requires at least one;
   empty means any genre, so no decision changes on upgrade.
   settings.autojoin_priorities (JSON NOT NULL, default
   '[{"type": "wishlist"}]'): the ordered priority list.
b. Data step on every settings row: the list is built from the old flags in
   today's fixed order, wishlist if wishlist_priority_enabled, then dlc if
   dlc_priority_enabled, then {"type": "ending_soon", "threshold_minutes":
   <ending_soon_threshold_minutes>} if ending_soon_priority_enabled. A
   disabled flag gives no item, so the first cycle after upgrade lifts and
   orders exactly as the last one did.
c. max_entries_per_cycle NULL becomes 10, the cap the worker always applied.
d. The four flag/threshold columns are dropped; autojoin_min_score and
   autojoin_min_reviews become nullable (NULL = filter off; stored values,
   0 included, are untouched); max_entries_per_cycle becomes NOT NULL with
   server default 10.
e. giveaways.eligibility_detail (JSON, nullable): the values behind
   eligibility_reason. NULL until a cycle re-evaluates the giveaway.
f. Rows whose eligibility_reason is the dropped 'price_above_max' code get
   eligibility_reason and eligibility_checked_at set to NULL.

Downgrade reverses every step: the four columns come back with their old
server defaults and are derived from the list (flag = type present,
threshold = the ending_soon item's value, else 60); both lists are dropped;
autojoin_min_score/min_reviews NULL become 7/1000 before NOT NULL is restored;
the cap becomes nullable again; eligibility_detail is dropped. An include
list is lost on downgrade, so the downgraded bot enters more giveaways than
the include list allowed. Step (f) cannot be undone (the nulled rows carried
no information the old engine could have produced), and codes the old engine
never wrote (budget_floor, cycle_cap, points_accumulating,
genre_not_included) stay in eligibility_reason until it re-evaluates them.

Revision ID: b7e2d9c4a1f6
Revises: f5b2d8c3a7e1
Create Date: 2026-11-04

"""
import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e2d9c4a1f6"
down_revision: str | Sequence[str] | None = "f5b2d8c3a7e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_THRESHOLD_MINUTES = 60


def _priorities_from_flags(
    wishlist: object, dlc: object, ending_soon: object, threshold: object
) -> list[dict[str, Any]]:
    """The priority list equivalent to the old flags, in today's order."""
    items: list[dict[str, Any]] = []
    if wishlist:
        items.append({"type": "wishlist"})
    if dlc:
        items.append({"type": "dlc"})
    if ending_soon:
        items.append({
            "type": "ending_soon",
            "threshold_minutes": threshold if isinstance(threshold, int) else DEFAULT_THRESHOLD_MINUTES,
        })
    return items


def _flags_from_priorities(raw: object) -> tuple[bool, bool, bool, int]:
    """The old (wishlist, dlc, ending_soon, threshold) values for a stored list."""
    items = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(items, list):
        raise ValueError(f"settings.autojoin_priorities is not a list: {raw!r}")
    by_type = {item.get("type"): item for item in items if isinstance(item, dict)}
    ending_soon = by_type.get("ending_soon")
    threshold = ending_soon.get("threshold_minutes") if ending_soon else None
    return (
        "wishlist" in by_type,
        "dlc" in by_type,
        ending_soon is not None,
        threshold if isinstance(threshold, int) else DEFAULT_THRESHOLD_MINUTES,
    )


def upgrade() -> None:
    """Upgrade schema."""
    # (a) the two new lists right after excluded_genres, in the order
    # included_genres, autojoin_priorities: insert_after must name a column
    # that exists before this batch, and columns added after the same anchor
    # keep their add order. Placement needs the table recreated.
    with op.batch_alter_table("settings", schema=None, recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "included_genres",
                sa.JSON(),
                nullable=False,
                server_default="[]",
                comment="Genre names auto-join requires at least one of (empty = any)",
            ),
            insert_after="excluded_genres",
        )
        batch_op.add_column(
            sa.Column(
                "autojoin_priorities",
                sa.JSON(),
                nullable=False,
                server_default='[{"type": "wishlist"}]',
                comment="Ordered auto-join priority list (list order = entry order)",
            ),
            insert_after="excluded_genres",
        )

    # (b) flags -> list, per row
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, wishlist_priority_enabled, dlc_priority_enabled, "
            "ending_soon_priority_enabled, ending_soon_threshold_minutes FROM settings"
        )
    ).fetchall()
    for row_id, wishlist, dlc, ending_soon, threshold in rows:
        bind.execute(
            sa.text("UPDATE settings SET autojoin_priorities = :priorities WHERE id = :id"),
            {"priorities": json.dumps(_priorities_from_flags(wishlist, dlc, ending_soon, threshold)), "id": row_id},
        )

    # (c) the cap the worker always applied
    op.execute("UPDATE settings SET max_entries_per_cycle = 10 WHERE max_entries_per_cycle IS NULL")

    # (d) drop the flags, nullable thresholds, NOT NULL cap
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.drop_column("wishlist_priority_enabled")
        batch_op.drop_column("dlc_priority_enabled")
        batch_op.drop_column("ending_soon_priority_enabled")
        batch_op.drop_column("ending_soon_threshold_minutes")
        batch_op.alter_column("autojoin_min_score", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("autojoin_min_reviews", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column(
            "max_entries_per_cycle",
            existing_type=sa.Integer(),
            nullable=False,
            server_default="10",
        )

    # (e) the decision detail
    with op.batch_alter_table("giveaways", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "eligibility_detail",
                sa.JSON(),
                nullable=True,
                comment="Values behind eligibility_reason (actual vs threshold); NULL = none recorded",
            )
        )

    # (f) the dropped price_above_max code
    op.execute(
        "UPDATE giveaways SET eligibility_reason = NULL, eligibility_checked_at = NULL "
        "WHERE eligibility_reason = 'price_above_max'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("giveaways", schema=None) as batch_op:
        batch_op.drop_column("eligibility_detail")

    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "wishlist_priority_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
                comment="Wishlist giveaways bypass autojoin filters and are entered first",
            )
        )
        batch_op.add_column(
            sa.Column(
                "dlc_priority_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
                comment="DLC giveaways bypass autojoin filters and are entered after wishlist ones",
            )
        )
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

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, autojoin_priorities FROM settings")).fetchall()
    for row_id, raw in rows:
        wishlist, dlc, ending_soon, threshold = _flags_from_priorities(raw)
        bind.execute(
            sa.text(
                "UPDATE settings SET wishlist_priority_enabled = :wishlist, dlc_priority_enabled = :dlc, "
                "ending_soon_priority_enabled = :ending_soon, ending_soon_threshold_minutes = :threshold "
                "WHERE id = :id"
            ),
            {"wishlist": wishlist, "dlc": dlc, "ending_soon": ending_soon, "threshold": threshold, "id": row_id},
        )

    op.execute(
        "UPDATE settings SET autojoin_min_score = COALESCE(autojoin_min_score, 7), "
        "autojoin_min_reviews = COALESCE(autojoin_min_reviews, 1000)"
    )

    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.drop_column("autojoin_priorities")
        batch_op.drop_column("included_genres")
        batch_op.alter_column("autojoin_min_score", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("autojoin_min_reviews", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column(
            "max_entries_per_cycle",
            existing_type=sa.Integer(),
            nullable=True,
            server_default=None,
            existing_server_default="10",
        )
