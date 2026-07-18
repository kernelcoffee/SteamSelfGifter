"""Autojoin eligibility evaluation.

A single, pure decision function — :func:`evaluate_eligibility` — decides whether
a giveaway should be auto-entered, and if not, *why*. It deliberately mirrors the
SQL filter in ``repositories.giveaway.GiveawayRepository.get_eligible`` condition
for condition, so the set of giveaways it labels ``ELIGIBLE`` is identical to what
that query returns. The difference is that this version also reports a reason for
every *rejected* giveaway, which the SQL (returning only survivors) cannot.

Semantics note (intentional): "unknown" Steam data counts as a failure, matching
the existing behaviour. A giveaway with no cached game row is rejected as
``NO_GAME_DATA`` whenever any game-based criterion is active; a game with an
unknown review score (stored as 0) fails ``min_score``; an unparseable/missing
release date fails ``max_game_age``.

Wishlist exception: giveaways flagged ``is_wishlist`` bypass the price and
game-quality criteria entirely — being on the user's Steam wishlist already
answers the question those filters approximate. They still respect the
active/hidden/entered checks.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

# === Reason codes (stored on Giveaway.eligibility_reason) ===
ELIGIBLE = "eligible"
EXPIRED = "expired"
HIDDEN = "hidden"
ENTERED = "entered"
PRICE_BELOW_MIN = "price_below_min"
PRICE_ABOVE_MAX = "price_above_max"
NO_GAME_DATA = "no_game_data"
SCORE_BELOW_MIN = "score_below_min"
REVIEWS_BELOW_MIN = "reviews_below_min"
GAME_TOO_OLD = "game_too_old"

# Human-readable labels for the UI / logs.
REASON_LABELS = {
    ELIGIBLE: "Eligible",
    EXPIRED: "Giveaway has ended",
    HIDDEN: "Hidden",
    ENTERED: "Already entered",
    PRICE_BELOW_MIN: "Price below minimum",
    PRICE_ABOVE_MAX: "Price above maximum",
    NO_GAME_DATA: "No Steam game data cached",
    SCORE_BELOW_MIN: "Review score below minimum",
    REVIEWS_BELOW_MIN: "Too few reviews",
    GAME_TOO_OLD: "Game older than allowed (or release date unknown)",
}


@dataclass(frozen=True)
class EligibilityCriteria:
    """The autojoin thresholds, sourced from Settings.

    ``min_score``/``min_reviews``/``max_game_age`` are optional: when set, they
    require cached game data (mirroring the JOIN in the SQL query).
    ``wishlist_priority`` controls the wishlist exception described in the
    module docstring; when off, wishlist giveaways pass the same filters as
    everything else.
    """

    min_price: int = 0
    max_price: int | None = None
    min_score: int | None = None
    min_reviews: int | None = None
    max_game_age: int | None = None
    wishlist_priority: bool = True

    @property
    def needs_game_data(self) -> bool:
        """Whether any criterion requires a cached game row to evaluate."""
        return (
            self.min_score is not None
            or self.min_reviews is not None
            or self.max_game_age is not None
        )


def evaluate_eligibility(giveaway: Any, game: Any, criteria: EligibilityCriteria, now: datetime) -> str:
    """Return the reason code describing this giveaway's autojoin outcome.

    Conditions are checked in a fixed precedence so that a multi-failure giveaway
    reports the most fundamental reason first. The set of giveaways returning
    ``ELIGIBLE`` is identical to ``GiveawayRepository.get_eligible``'s result set.

    Args:
        giveaway: the Giveaway ORM object.
        game: the matching Game ORM object, or ``None`` if not cached.
        criteria: the active autojoin thresholds.
        now: current UTC time (naive, to match stored naive datetimes).
    """
    # Active window — matches `end_time IS NOT NULL AND end_time > now`.
    if giveaway.end_time is None or giveaway.end_time <= now:
        return EXPIRED

    if giveaway.is_hidden:
        return HIDDEN

    if giveaway.is_entered:
        return ENTERED

    # Wishlist games are wanted by definition: they bypass the price and
    # game-quality filters (matches the `is_wishlist OR (...)` in the SQL),
    # unless the user turned wishlist priority off.
    if criteria.wishlist_priority and giveaway.is_wishlist:
        return ELIGIBLE

    # Price range — matches `price >= min_price [AND price <= max_price]`.
    if giveaway.price < criteria.min_price:
        return PRICE_BELOW_MIN
    if criteria.max_price is not None and giveaway.price > criteria.max_price:
        return PRICE_ABOVE_MAX

    # Game-based criteria require a cached game (the SQL uses an inner JOIN).
    if criteria.needs_game_data and game is None:
        return NO_GAME_DATA

    if criteria.min_score is not None and (game.review_score or 0) < criteria.min_score:
        return SCORE_BELOW_MIN

    if criteria.min_reviews is not None and (game.total_reviews or 0) < criteria.min_reviews:
        return REVIEWS_BELOW_MIN

    if criteria.max_game_age is not None:
        # release_date is stored as ISO "YYYY-MM-DD"; lexicographic compare
        # matches the SQL `Game.release_date >= 'YYYY-01-01'`. Missing dates fail.
        min_release_date = f"{now.year - criteria.max_game_age}-01-01"
        if game.release_date is None or game.release_date < min_release_date:
            return GAME_TOO_OLD

    return ELIGIBLE
