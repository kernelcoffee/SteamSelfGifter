"""Unit tests for the auto-join decision engine (services.eligibility).

Pure tests: gates, priority match and exemption, filters and their detail,
the include list, ordering, the cycle plan, explanations and the registry.
Lift-and-order parity with the replaced engine is guarded separately by
test_eligibility_golden.py; DB-backed cycle tests live in
test_services_giveaway_service.py.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from services.eligibility import (
    BUDGET_FLOOR,
    CYCLE_CAP,
    ELIGIBLE,
    ENTERED,
    EXPIRED,
    FILTERS,
    GAME_TOO_OLD,
    GATES,
    GENRE_EXCLUDED,
    GENRE_NOT_INCLUDED,
    HIDDEN,
    MAX_PRIORITY_ITEMS,
    NO_GAME_DATA,
    OUTCOMES,
    POINTS_ACCUMULATING,
    PRICE_BELOW_MIN,
    PRIORITY_TYPES,
    REASON_LABELS,
    REVIEWS_BELOW_MIN,
    RULES,
    SCORE_BELOW_MIN,
    UNSAFE,
    AutoJoinPolicy,
    CycleBudget,
    Decision,
    InvalidPolicyError,
    PolicyFields,
    PriorityItem,
    decide,
    explain,
    fold_genres,
    gate_of,
    kind_of,
    normalize_genre_list,
    order_candidates,
    parse_priorities,
    plan_cycle,
    policy_from_settings,
    registry_as_data,
)

NOW = datetime(2026, 6, 17, 12, 0, 0)

WISHLIST = PriorityItem("wishlist")
DLC = PriorityItem("dlc")


def _soon(minutes: int = 60) -> PriorityItem:
    return PriorityItem("ending_soon", threshold_minutes=minutes)


def _gw(**kw: Any) -> Any:
    """A giveaway stand-in (only the attributes the engine reads)."""
    base: dict[str, Any] = dict(
        code="G",
        end_time=NOW + timedelta(days=1),
        is_hidden=False,
        is_entered=False,
        is_safe=None,
        safety_score=None,
        is_wishlist=False,
        is_dlc=False,
        price=50,
        game_id=620,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _game(**kw: Any) -> Any:
    base: dict[str, Any] = dict(review_score=9, total_reviews=5000, release_date="2020-01-01", genres=["Puzzle"])
    base.update(kw)
    return SimpleNamespace(**base)


def _policy(**kw: Any) -> AutoJoinPolicy:
    base: dict[str, Any] = dict(min_price=10, min_score=7, min_reviews=1000)
    base.update(kw)
    return AutoJoinPolicy(**base)


def _settings(**kw: Any) -> Any:
    """A settings row stand-in with every field policy_from_settings reads."""
    base: dict[str, Any] = dict(
        autojoin_min_price=10,
        autojoin_min_score=7,
        autojoin_min_reviews=1000,
        autojoin_max_game_age=None,
        excluded_genres=[],
        included_genres=[],
        autojoin_priorities=[{"type": "wishlist"}],
        autojoin_start_at=350,
        autojoin_stop_at=200,
        max_entries_per_cycle=10,
        auto_hide_unsafe=True,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ----------------------------------------------------------------------------
# Gates
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("end_time", [None, NOW, NOW - timedelta(hours=1)])
def test_expired_gate_beats_everything(end_time: datetime | None) -> None:
    giveaway = _gw(end_time=end_time, is_hidden=True, is_entered=True, is_wishlist=True)
    decision = decide(giveaway, None, _policy(priorities=(WISHLIST,)), NOW)
    assert decision == Decision(code=EXPIRED, detail={}, lifted_by=None, priority=None, rank=1)


def test_hidden_gate_is_never_lifted_by_wishlist() -> None:
    decision = decide(_gw(is_hidden=True, is_wishlist=True), _game(), _policy(priorities=(WISHLIST,)), NOW)
    assert (decision.code, decision.detail, decision.lifted_by) == (HIDDEN, {}, None)


def test_entered_gate() -> None:
    decision = decide(_gw(is_entered=True), _game(), _policy(), NOW)
    assert (decision.code, decision.detail) == (ENTERED, {})


@pytest.mark.parametrize("score", [60, 10])
def test_unsafe_gate_records_safety_score_and_beats_wishlist(score: int) -> None:
    giveaway = _gw(is_safe=False, safety_score=score, is_wishlist=True)
    decision = decide(giveaway, _game(), _policy(priorities=(WISHLIST,)), NOW)
    assert (decision.code, decision.detail, decision.lifted_by) == (UNSAFE, {"safety_score": score}, None)


@pytest.mark.parametrize("is_safe", [None, True])
def test_unchecked_or_safe_passes_the_gate(is_safe: bool | None) -> None:
    assert decide(_gw(is_safe=is_safe), _game(), _policy(), NOW).code == ELIGIBLE


def test_gate_precedence_order() -> None:
    assert [rule.code for rule in GATES] == [EXPIRED, HIDDEN, ENTERED, UNSAFE]
    assert decide(_gw(is_hidden=True, is_entered=True, is_safe=False), _game(), _policy(), NOW).code == HIDDEN
    assert decide(_gw(is_entered=True, is_safe=False), _game(), _policy(), NOW).code == ENTERED


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (dict(end_time=None), (EXPIRED, {})),
        (dict(is_hidden=True, is_safe=False), (HIDDEN, {})),
        (dict(is_entered=True), (ENTERED, {})),
        (dict(is_safe=False, safety_score=60), (UNSAFE, {"safety_score": 60})),
        # No gate: the filters are not run (price 1 < 10 would fail them).
        (dict(price=1, is_safe=True), None),
    ],
)
def test_gate_of_runs_only_the_gates_in_order(row: dict[str, Any], expected: tuple[str, dict] | None) -> None:
    giveaway = _gw(**row)
    assert gate_of(giveaway, _policy(), NOW) == expected
    if expected is not None:
        decision = decide(giveaway, None, _policy(), NOW)
        assert (decision.code, decision.detail) == expected


# ----------------------------------------------------------------------------
# Priority match and exemption
# ----------------------------------------------------------------------------

def _bad_giveaway(**kw: Any) -> Any:
    """Price 1 < min 10 and (with the game below) an excluded genre."""
    return _gw(price=1, **kw)


def test_wishlist_item_lifts_every_filter() -> None:
    policy = _policy(priorities=(WISHLIST,), excluded_genres=frozenset({"Action"}))
    decision = decide(_bad_giveaway(is_wishlist=True), None, policy, NOW)
    assert decision == Decision(
        code=ELIGIBLE,
        detail={"priority": "wishlist", "rank": 0, "lifted_by": "wishlist"},
        lifted_by="wishlist",
        priority="wishlist",
        rank=0,
    )
    assert decision.enter is True


@pytest.mark.parametrize("priorities", [(), (DLC,), (_soon(),)])
def test_wishlist_without_its_item_obeys_the_filters(priorities: tuple[PriorityItem, ...]) -> None:
    decision = decide(_bad_giveaway(is_wishlist=True), None, _policy(priorities=priorities), NOW)
    assert (decision.code, decision.detail) == (PRICE_BELOW_MIN, {"price": 1, "min_price": 10})
    assert decision.enter is False


def test_dlc_item_lifts_every_filter() -> None:
    game = _game(genres=["Action"], review_score=1)
    policy = _policy(priorities=(DLC,), excluded_genres=frozenset({"action"}))
    decision = decide(_bad_giveaway(is_dlc=True), game, policy, NOW)
    assert (decision.code, decision.lifted_by, decision.priority, decision.rank) == (ELIGIBLE, "dlc", "dlc", 0)


def test_dlc_giveaway_with_only_the_wishlist_item_obeys_the_filters() -> None:
    decision = decide(_bad_giveaway(is_dlc=True), None, _policy(priorities=(WISHLIST,)), NOW)
    assert decision.code == PRICE_BELOW_MIN


def test_ending_soon_never_lifts() -> None:
    giveaway = _gw(end_time=NOW + timedelta(minutes=30))
    policy = _policy(priorities=(_soon(60),), excluded_genres=frozenset({"action"}))
    decision = decide(giveaway, _game(genres=["Action"]), policy, NOW)
    assert (decision.code, decision.detail) == (GENRE_EXCLUDED, {"genre": "Action"})
    assert (decision.priority, decision.rank, decision.lifted_by) == ("ending_soon", 0, None)


def test_any_exempt_match_lifts_even_when_not_first() -> None:
    giveaway = _gw(is_wishlist=True, end_time=NOW + timedelta(minutes=30))
    decision = decide(giveaway, _game(review_score=6), _policy(priorities=(_soon(60), WISHLIST)), NOW)
    assert (decision.code, decision.priority, decision.rank, decision.lifted_by) == (
        ELIGIBLE, "ending_soon", 0, "wishlist",
    )
    assert decision.detail == {"priority": "ending_soon", "rank": 0, "lifted_by": "wishlist"}


def test_first_match_gives_priority_and_rank() -> None:
    giveaway = _gw(is_wishlist=True, is_dlc=True)
    decision = decide(giveaway, _game(), _policy(priorities=(DLC, WISHLIST)), NOW)
    assert (decision.priority, decision.rank, decision.lifted_by) == ("dlc", 0, "dlc")


def test_unmatched_candidate_ranks_after_the_list() -> None:
    decision = decide(_gw(), _game(), _policy(priorities=(WISHLIST, DLC)), NOW)
    assert decision.detail == {"priority": None, "rank": 2, "lifted_by": None}


# ----------------------------------------------------------------------------
# Filters: precedence and detail
# ----------------------------------------------------------------------------

def test_filter_registry_order_and_settings() -> None:
    assert [rule.code for rule in FILTERS] == [
        PRICE_BELOW_MIN, GENRE_EXCLUDED, GENRE_NOT_INCLUDED, NO_GAME_DATA,
        SCORE_BELOW_MIN, REVIEWS_BELOW_MIN, GAME_TOO_OLD,
    ]
    assert [rule.setting for rule in FILTERS] == [
        "autojoin_min_price", "excluded_genres", "included_genres", None,
        "autojoin_min_score", "autojoin_min_reviews", "autojoin_max_game_age",
    ]


def test_price_beats_score_and_genre() -> None:
    policy = _policy(excluded_genres=frozenset({"action"}))
    decision = decide(_gw(price=5), _game(review_score=6, genres=["Action"]), policy, NOW)
    assert (decision.code, decision.detail) == (PRICE_BELOW_MIN, {"price": 5, "min_price": 10})


def test_genre_beats_score() -> None:
    policy = _policy(excluded_genres=frozenset({"action"}))
    decision = decide(_gw(), _game(review_score=6, genres=["Indie", "ACTION"]), policy, NOW)
    assert (decision.code, decision.detail) == (GENRE_EXCLUDED, {"genre": "ACTION"})


def test_missing_game_with_a_quality_threshold_is_no_game_data() -> None:
    decision = decide(_gw(), None, _policy(), NOW)
    assert (decision.code, decision.detail) == (NO_GAME_DATA, {})


def test_score_beats_reviews_and_age() -> None:
    game = _game(review_score=6, total_reviews=10, release_date="1999-01-01")
    decision = decide(_gw(), game, _policy(max_game_age=5), NOW)
    assert (decision.code, decision.detail) == (SCORE_BELOW_MIN, {"score": 6, "min_score": 7})


def test_reviews_below_min_detail() -> None:
    decision = decide(_gw(), _game(total_reviews=500), _policy(), NOW)
    assert (decision.code, decision.detail) == (REVIEWS_BELOW_MIN, {"reviews": 500, "min_reviews": 1000})


def test_game_too_old_detail() -> None:
    decision = decide(_gw(), _game(release_date="2005-01-01"), _policy(max_game_age=5), NOW)
    assert (decision.code, decision.detail) == (GAME_TOO_OLD, {"release_date": "2005-01-01", "max_game_age": 5})


def test_game_age_cutoff_is_january_first() -> None:
    policy = _policy(max_game_age=5)  # NOW is 2026: cutoff 2021-01-01
    assert decide(_gw(), _game(release_date="2021-01-01"), policy, NOW).code == ELIGIBLE
    assert decide(_gw(), _game(release_date="2020-12-31"), policy, NOW).code == GAME_TOO_OLD


def test_all_filters_pass() -> None:
    decision = decide(_gw(), _game(), _policy(max_game_age=10, excluded_genres=frozenset({"action"})), NOW)
    assert decision.code == ELIGIBLE


# ----------------------------------------------------------------------------
# Unknown Steam data (D2: fail closed for quality, pass for exclusion)
# ----------------------------------------------------------------------------

def test_min_score_zero_still_needs_game_data() -> None:
    assert decide(_gw(), None, _policy(min_score=0, min_reviews=None), NOW).code == NO_GAME_DATA


def test_every_quality_filter_off_does_not_need_game_data() -> None:
    policy = _policy(min_score=None, min_reviews=None, max_game_age=None, excluded_genres=frozenset({"action"}))
    assert policy.needs_game_data is False
    assert decide(_gw(), None, policy, NOW).code == ELIGIBLE


@pytest.mark.parametrize("genres", [None, []])
def test_unknown_or_empty_genres_pass_the_exclusion(genres: list[str] | None) -> None:
    policy = _policy(excluded_genres=frozenset({"action"}))
    assert decide(_gw(), _game(genres=genres), policy, NOW).code == ELIGIBLE


@pytest.mark.parametrize("score", [None, 0])
def test_unknown_score_counts_as_zero(score: int | None) -> None:
    decision = decide(_gw(), _game(review_score=score), _policy(min_score=1, min_reviews=None), NOW)
    assert (decision.code, decision.detail) == (SCORE_BELOW_MIN, {"score": 0, "min_score": 1})


def test_unknown_review_count_counts_as_zero() -> None:
    decision = decide(_gw(), _game(total_reviews=None), _policy(min_score=None, min_reviews=1), NOW)
    assert (decision.code, decision.detail) == (REVIEWS_BELOW_MIN, {"reviews": 0, "min_reviews": 1})


def test_unknown_release_date_fails_the_age_limit() -> None:
    decision = decide(_gw(), _game(release_date=None), _policy(max_game_age=5), NOW)
    assert (decision.code, decision.detail) == (GAME_TOO_OLD, {"release_date": None, "max_game_age": 5})


def test_score_and_reviews_none_are_off() -> None:
    game = _game(review_score=0, total_reviews=0)
    assert decide(_gw(), game, _policy(min_score=None, min_reviews=None), NOW).code == ELIGIBLE


# ----------------------------------------------------------------------------
# Genre matching
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("excluded, stored", [("ACTION", "Action"), ("action", "ACTION"), (" Action ", "aCtIoN")])
def test_genre_exclusion_is_case_insensitive(excluded: str, stored: str) -> None:
    policy = _policy(excluded_genres=fold_genres([excluded]))
    assert decide(_gw(), _game(genres=[stored]), policy, NOW).detail == {"genre": stored}


def test_genre_folding_is_ascii_only() -> None:
    policy = _policy(excluded_genres=frozenset({"ACCIÓN"}))
    assert policy.excluded_genres == frozenset({"acciÓn"})
    assert decide(_gw(), _game(genres=["Acción"]), policy, NOW).code == ELIGIBLE
    assert decide(_gw(), _game(genres=["AcciÓn"]), policy, NOW).code == GENRE_EXCLUDED


def test_fold_genres_strips_and_drops_empties_and_non_strings() -> None:
    assert fold_genres([" Action ", "", "  ", "INDIE", "indie", 3]) == frozenset({"action", "indie"})


def test_normalized_exclusions_match_each_listed_spelling() -> None:
    """The normaliser keeps spellings the matcher folds differently, so a
    list holding both "Éducation" and "éducation" excludes "éducation"."""
    excluded = normalize_genre_list(["Éducation", "éducation"], "excluded_genres")
    policy = _policy(excluded_genres=frozenset(excluded))
    assert decide(_gw(), _game(genres=["éducation"]), policy, NOW).code == GENRE_EXCLUDED


def test_non_string_genres_are_ignored_by_the_exclusion() -> None:
    policy = _policy(excluded_genres=frozenset({"action"}))
    assert decide(_gw(), _game(genres=[7, None]), policy, NOW).code == ELIGIBLE


# ----------------------------------------------------------------------------
# Include list (D13)
# ----------------------------------------------------------------------------

def _include(*genres: str, **kw: Any) -> AutoJoinPolicy:
    return _policy(included_genres=frozenset(genres), **kw)


def test_include_list_match_is_ascii_case_insensitive() -> None:
    decision = decide(_gw(), _game(genres=["Action", "indie"]), _include("RPG", "Indie"), NOW)
    assert decision.code == ELIGIBLE


def test_include_list_no_match_records_the_cached_genres() -> None:
    decision = decide(_gw(), _game(genres=["Action", "Horror"]), _include("RPG", "Indie"), NOW)
    assert (decision.code, decision.detail) == (GENRE_NOT_INCLUDED, {"genres": ["Action", "Horror"]})
    assert explain(decision.code, decision.detail) == "None of its genres (Action, Horror) is on your included list"


def test_include_list_fails_closed_on_empty_genres() -> None:
    decision = decide(_gw(), _game(genres=[]), _include("RPG"), NOW)
    assert (decision.code, decision.detail) == (GENRE_NOT_INCLUDED, {"genres": []})
    assert explain(decision.code, decision.detail) == "It has no Steam genres, so it cannot match your included list"


@pytest.mark.parametrize("game", [None, SimpleNamespace(genres=None, review_score=9, total_reviews=5000,
                                                        release_date="2024-01-01")])
def test_include_list_fails_closed_on_unknown_genres(game: Any) -> None:
    decision = decide(_gw(), game, _include("RPG"), NOW)
    assert (decision.code, decision.detail) == (GENRE_NOT_INCLUDED, {"genres": None})
    assert explain(decision.code, decision.detail) == (
        "Steam genres not cached yet; unknown genres fail your included-genre filter; checked again next cycle"
    )


def test_include_list_fires_before_no_game_data_even_with_quality_filters_off() -> None:
    policy = _include("RPG", min_score=None, min_reviews=None, max_game_age=None)
    decision = decide(_gw(), None, policy, NOW)
    assert (decision.code, decision.detail) == (GENRE_NOT_INCLUDED, {"genres": None})


def test_include_list_fires_before_no_game_data_with_quality_filters_on() -> None:
    assert decide(_gw(), None, _include("RPG"), NOW).code == GENRE_NOT_INCLUDED


def test_empty_include_list_is_inert() -> None:
    assert decide(_gw(), _game(genres=[]), _policy(included_genres=frozenset()), NOW).code == ELIGIBLE


@pytest.mark.parametrize("genres, expected, detail", [
    (["Action"], GENRE_EXCLUDED, {"genre": "Action"}),
    (["RPG"], ELIGIBLE, {"priority": None, "rank": 0, "lifted_by": None}),
    (["Indie"], GENRE_NOT_INCLUDED, {"genres": ["Indie"]}),
])
def test_exclusion_wins_over_inclusion(genres: list[str], expected: str, detail: dict[str, Any]) -> None:
    policy = _include("Action", "RPG", excluded_genres=frozenset({"action"}))
    decision = decide(_gw(), _game(genres=genres), policy, NOW)
    assert (decision.code, decision.detail) == (expected, detail)


def test_include_precedence_price_first() -> None:
    assert decide(_gw(price=5), _game(genres=["Indie"]), _include("RPG"), NOW).code == PRICE_BELOW_MIN


def test_include_precedence_exclusion_before_inclusion() -> None:
    policy = _include("RPG", excluded_genres=frozenset({"action"}))
    assert decide(_gw(), _game(genres=["Action"]), policy, NOW).code == GENRE_EXCLUDED


def test_include_precedence_inclusion_before_score() -> None:
    decision = decide(_gw(), _game(genres=["Indie"], review_score=6), _include("RPG"), NOW)
    assert decision.code == GENRE_NOT_INCLUDED


@pytest.mark.parametrize("flag, item", [("is_wishlist", WISHLIST), ("is_dlc", DLC)])
def test_exemption_skips_both_genre_lists(flag: str, item: PriorityItem) -> None:
    policy = _include("RPG", excluded_genres=frozenset({"action"}), priorities=(item,))
    decision = decide(_gw(**{flag: True}), _game(genres=["Action"]), policy, NOW)
    assert (decision.code, decision.lifted_by) == (ELIGIBLE, item.type)


def test_ending_soon_alone_does_not_skip_the_include_list() -> None:
    policy = _include("RPG", priorities=(_soon(60),))
    decision = decide(_gw(end_time=NOW + timedelta(minutes=30)), _game(genres=["Indie"]), policy, NOW)
    assert decision.code == GENRE_NOT_INCLUDED


def test_include_label_lists_at_most_six_genres() -> None:
    genres = ["A", "B", "C", "D", "E", "F", "G", "H"]
    decision = decide(_gw(), _game(genres=genres), _include("RPG"), NOW)
    assert explain(decision.code, decision.detail) == "None of its genres (A, B, C, D, E, F, …) is on your included list"


def test_include_label_with_exactly_six_genres_is_not_cut() -> None:
    label = explain(GENRE_NOT_INCLUDED, {"genres": ["A", "B", "C", "D", "E", "F"]})
    assert label == "None of its genres (A, B, C, D, E, F) is on your included list"


# ----------------------------------------------------------------------------
# Ordering
# ----------------------------------------------------------------------------

def _order(pool: list[Any], policy: AutoJoinPolicy, game: Any = None) -> list[str]:
    decided = [(g, decide(g, game, policy, NOW)) for g in pool]
    return [g.code for g, _ in order_candidates(decided, policy, NOW)]


def test_order_follows_the_list_with_groups() -> None:
    soon = NOW + timedelta(minutes=30)
    pool = [  # price descending, one flag each
        _gw(code="rich", price=900),
        _gw(code="soon_late", price=500, end_time=NOW + timedelta(minutes=50)),
        _gw(code="wish_hi", price=400, is_wishlist=True),
        _gw(code="dlc_hi", price=300, is_dlc=True),
        _gw(code="soon_early", price=200, end_time=NOW + timedelta(minutes=10)),
        _gw(code="mid", price=100),
        _gw(code="wish_lo", price=40, is_wishlist=True, end_time=soon),
        _gw(code="dlc_lo", price=30, is_dlc=True),
    ]
    policy = AutoJoinPolicy(priorities=(DLC, WISHLIST, _soon(60)))
    assert _order(pool, policy) == [
        "dlc_hi", "dlc_lo", "wish_hi", "wish_lo", "soon_early", "soon_late", "rich", "mid",
    ]


def test_later_exempt_match_breaks_ties_inside_a_group() -> None:
    """As in the replaced engine: inside the wishlist group, giveaways also
    matching the dlc item come first; price order otherwise."""
    pool = [
        _gw(code="wish_hi", price=400, is_wishlist=True),
        _gw(code="both_lo", price=10, is_wishlist=True, is_dlc=True),
    ]
    assert _order(pool, AutoJoinPolicy(priorities=(WISHLIST, DLC))) == ["both_lo", "wish_hi"]
    assert _order(pool, AutoJoinPolicy(priorities=(WISHLIST,))) == ["wish_hi", "both_lo"]


def test_ending_soon_after_an_exempt_match_does_not_reorder_its_group() -> None:
    pool = [
        _gw(code="wish_far", price=400, is_wishlist=True),
        _gw(code="wish_soon", price=10, is_wishlist=True, end_time=NOW + timedelta(minutes=5)),
    ]
    assert _order(pool, AutoJoinPolicy(priorities=(WISHLIST, _soon(60)))) == ["wish_far", "wish_soon"]


def test_ending_soon_boundary() -> None:
    at = _gw(code="at", price=10, end_time=NOW + timedelta(minutes=60))
    past = _gw(code="past", price=20, end_time=NOW + timedelta(minutes=61))
    policy = AutoJoinPolicy(priorities=(_soon(60),))
    assert decide(at, None, policy, NOW).priority == "ending_soon"
    assert decide(past, None, policy, NOW).priority is None
    assert _order([past, at], policy) == ["at", "past"]


def test_ending_soon_matcher_never_matches_an_unknown_end_time() -> None:
    matches = PRIORITY_TYPES["ending_soon"].matches
    assert matches(_gw(end_time=None), _soon(10080), NOW) is False
    assert matches(_gw(end_time=NOW + timedelta(minutes=1)), PriorityItem("ending_soon"), NOW) is False


def test_end_time_none_is_expired_before_ordering() -> None:
    decision = decide(_gw(end_time=None), None, AutoJoinPolicy(priorities=(_soon(60),)), NOW)
    assert (decision.code, decision.priority) == (EXPIRED, None)


def test_empty_list_keeps_price_order_and_wishlist_dlc_obey_filters() -> None:
    pool = [
        _gw(code="a", price=90),
        _gw(code="wish_cheap", price=5, is_wishlist=True),
        _gw(code="b", price=60, end_time=NOW + timedelta(minutes=5)),
        _gw(code="dlc_ok", price=20, is_dlc=True),
    ]
    policy = AutoJoinPolicy(min_price=10)
    assert _order(pool, policy) == ["a", "b", "dlc_ok"]
    assert decide(pool[1], None, policy, NOW).code == PRICE_BELOW_MIN


# ----------------------------------------------------------------------------
# Cycle plan
# ----------------------------------------------------------------------------

def _eligible(code: str, price: int) -> tuple[Any, Decision]:
    detail = {"priority": None, "rank": 0, "lifted_by": None}
    return _gw(code=code, price=price), Decision(code=ELIGIBLE, detail=detail)


def _plan_codes(plan: list[tuple[Any, str, dict[str, Any]]]) -> list[tuple[str, str, dict[str, Any]]]:
    return [(g.code, code, detail) for g, code, detail in plan]


def test_plan_with_unknown_points_keeps_every_candidate_eligible() -> None:
    candidates = [_eligible("A", 60), _eligible("B", 40)]
    plan = plan_cycle(candidates, None, AutoJoinPolicy(start_at=0, stop_at=0))
    assert [code for _, code, _ in plan] == [ELIGIBLE, ELIGIBLE]
    assert plan[0][2] == {"priority": None, "rank": 0, "lifted_by": None}


def test_plan_below_start_threshold_accumulates() -> None:
    plan = plan_cycle([_eligible("A", 60), _eligible("B", 40)], 300, AutoJoinPolicy(start_at=350, stop_at=200))
    assert _plan_codes(plan) == [
        ("A", POINTS_ACCUMULATING, {"points": 300, "start_at": 350}),
        ("B", POINTS_ACCUMULATING, {"points": 300, "start_at": 350}),
    ]


def test_plan_budget_floor_skips_not_stops() -> None:
    plan = plan_cycle([_eligible("A", 60), _eligible("B", 40)], 250, AutoJoinPolicy(start_at=0, stop_at=200))
    assert _plan_codes(plan) == [
        ("A", BUDGET_FLOOR, {"price": 60, "points": 250, "stop_at": 200}),
        ("B", ELIGIBLE, {"priority": None, "rank": 0, "lifted_by": None}),
    ]


def test_plan_cycle_cap() -> None:
    candidates = [_eligible("A", 10), _eligible("B", 10), _eligible("C", 10)]
    plan = plan_cycle(candidates, 1000, AutoJoinPolicy(max_entries_per_cycle=2))
    assert [code for _, code, _ in plan] == [ELIGIBLE, ELIGIBLE, CYCLE_CAP]
    assert plan[2][2] == {"cap": 2}


def test_plan_cap_counts_attempts_not_budget_skips() -> None:
    candidates = [_eligible("BIG", 900), _eligible("A", 10), _eligible("B", 10), _eligible("C", 10)]
    plan = plan_cycle(candidates, 100, AutoJoinPolicy(max_entries_per_cycle=2))
    assert [code for _, code, _ in plan] == [BUDGET_FLOOR, ELIGIBLE, ELIGIBLE, CYCLE_CAP]


def test_plan_tracks_the_running_balance() -> None:
    plan = plan_cycle([_eligible("A", 60), _eligible("B", 50)], 500, AutoJoinPolicy(start_at=0, stop_at=400))
    assert _plan_codes(plan) == [
        ("A", ELIGIBLE, {"priority": None, "rank": 0, "lifted_by": None}),
        ("B", BUDGET_FLOOR, {"price": 50, "points": 440, "stop_at": 400}),
    ]


def test_plan_at_the_start_threshold_spends() -> None:
    plan = plan_cycle([_eligible("A", 10)], 350, AutoJoinPolicy(start_at=350, stop_at=0))
    assert [code for _, code, _ in plan] == [ELIGIBLE]


def test_cycle_budget_failed_attempt_spends_nothing() -> None:
    """The entry loop's view: FIRST (60P) fails, so SECOND (50P) still fits
    500 - 50 >= 400, though the plan priced it out assuming FIRST succeeds."""
    budget = CycleBudget.for_cycle(500, AutoJoinPolicy(stop_at=400, max_entries_per_cycle=10))
    assert budget.skip(60) is None
    budget.attempt(0)
    assert budget.skip(50) is None
    budget.attempt(50)
    assert (budget.points, budget.attempts) == (450, 2)
    assert budget.skip(60) == (BUDGET_FLOOR, {"price": 60, "points": 450, "stop_at": 400})


def test_cycle_budget_cap_counts_failed_attempts_first() -> None:
    budget = CycleBudget.for_cycle(1000, AutoJoinPolicy(stop_at=0, max_entries_per_cycle=1))
    budget.attempt(0)
    # The cap wins over the floor once reached, whatever the price.
    assert budget.skip(5000) == (CYCLE_CAP, {"cap": 1})


def test_cycle_budget_floor_is_inclusive() -> None:
    budget = CycleBudget.for_cycle(250, AutoJoinPolicy(stop_at=200))
    assert budget.skip(50) is None
    assert budget.skip(51) == (BUDGET_FLOOR, {"price": 51, "points": 250, "stop_at": 200})


# ----------------------------------------------------------------------------
# Priority list parsing
# ----------------------------------------------------------------------------

def test_parse_priorities_accepts_every_type_in_order() -> None:
    items = parse_priorities([
        {"type": "dlc"}, {"type": "ending_soon", "threshold_minutes": 120}, {"type": "wishlist"},
    ])
    assert items == (DLC, _soon(120), WISHLIST)
    assert [item.to_dict() for item in items] == [
        {"type": "dlc"}, {"type": "ending_soon", "threshold_minutes": 120}, {"type": "wishlist"},
    ]


@pytest.mark.parametrize("threshold", [5, 10080])
def test_parse_priorities_threshold_bounds(threshold: int) -> None:
    assert parse_priorities([{"type": "ending_soon", "threshold_minutes": threshold}]) == (_soon(threshold),)


def test_parse_priorities_empty_list() -> None:
    assert parse_priorities([]) == ()


@pytest.mark.parametrize("raw, message", [
    ("wishlist", "must be a list"),
    (None, "must be a list"),
    ([{"type": "wishlist"}, {"type": "dlc"}, {"type": "ending_soon", "threshold_minutes": 60},
      {"type": "wishlist"}], "at most 3"),
    (["wishlist"], "must be an object"),
    ([{}], "string 'type'"),
    ([{"type": 3}], "string 'type'"),
    ([{"type": "bogus"}], "unknown priority type 'bogus'"),
    ([{"type": "wishlist"}, {"type": "wishlist"}], "duplicate priority type 'wishlist'"),
    ([{"type": "wishlist", "threshold_minutes": 10}], "accepts only: type"),
    ([{"type": "ending_soon"}], "requires threshold_minutes"),
    ([{"type": "ending_soon", "threshold_minutes": 4}], "between 5 and 10080"),
    ([{"type": "ending_soon", "threshold_minutes": 10081}], "between 5 and 10080"),
    ([{"type": "ending_soon", "threshold_minutes": "60"}], "must be an integer"),
    ([{"type": "ending_soon", "threshold_minutes": True}], "must be an integer"),
])
def test_parse_priorities_rejections(raw: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_priorities(raw)


def test_max_priority_items_is_the_number_of_types() -> None:
    assert MAX_PRIORITY_ITEMS == len(PRIORITY_TYPES) == 3


# ----------------------------------------------------------------------------
# Policy builder
# ----------------------------------------------------------------------------

def test_policy_from_settings_reads_every_field() -> None:
    settings = _settings(
        autojoin_min_price=None, autojoin_min_score=None, autojoin_min_reviews=0, autojoin_max_game_age=3,
        excluded_genres=[" Action "], included_genres=["RPG"],
        autojoin_priorities=[{"type": "ending_soon", "threshold_minutes": 90}, {"type": "dlc"}],
        autojoin_start_at=None, autojoin_stop_at=None, max_entries_per_cycle=None, auto_hide_unsafe=False,
    )
    assert policy_from_settings(settings) == AutoJoinPolicy(
        min_price=0, min_score=None, min_reviews=0, max_game_age=3,
        excluded_genres=frozenset({"action"}), included_genres=frozenset({"rpg"}),
        priorities=(_soon(90), DLC), start_at=0, stop_at=0, max_entries_per_cycle=10, auto_hide_unsafe=False,
    )


def test_policy_from_settings_tolerates_null_genre_lists() -> None:
    policy = policy_from_settings(_settings(excluded_genres=None, included_genres=None))
    assert (policy.excluded_genres, policy.included_genres) == (frozenset(), frozenset())


@pytest.mark.parametrize("stored", [[{"type": "bogus"}], [{"type": "dlc"}, {"type": "dlc"}],
                                    [{"type": "ending_soon", "threshold_minutes": 4}]])
def test_policy_from_settings_fails_closed_on_a_bad_stored_list(stored: list[dict[str, Any]]) -> None:
    with pytest.raises(ValueError):
        policy_from_settings(_settings(autojoin_priorities=stored))


def _fields(**kw: Any) -> PolicyFields:
    base: dict[str, Any] = dict(
        autojoin_min_price=0, autojoin_min_score=3, autojoin_min_reviews=None, autojoin_max_game_age=None,
        excluded_genres=["Horror"], included_genres=[], autojoin_priorities=[{"type": "dlc"}],
    )
    base.update(kw)
    return PolicyFields(**base)


def test_policy_override_replaces_the_seven_fields_and_keeps_the_budget() -> None:
    settings = _settings(autojoin_priorities=[{"type": "bogus"}], autojoin_start_at=400, autojoin_stop_at=100,
                         max_entries_per_cycle=4, auto_hide_unsafe=False)
    policy = policy_from_settings(settings, _fields())
    assert policy == AutoJoinPolicy(
        min_price=0, min_score=3, min_reviews=None, max_game_age=None,
        excluded_genres=frozenset({"horror"}), included_genres=frozenset(), priorities=(DLC,),
        start_at=400, stop_at=100, max_entries_per_cycle=4, auto_hide_unsafe=False,
    )


def test_policy_override_with_a_bad_list_raises() -> None:
    with pytest.raises(ValueError, match="unknown priority type"):
        policy_from_settings(_settings(), _fields(autojoin_priorities=[{"type": "bogus"}]))


def test_policy_from_settings_names_a_bad_priority_list() -> None:
    with pytest.raises(InvalidPolicyError) as raised:
        policy_from_settings(_settings(autojoin_priorities=[{"type": "bogus"}]))
    assert raised.value.setting == "autojoin_priorities"
    assert str(raised.value) == "Auto-join priorities setting is invalid: unknown priority type 'bogus'"


@pytest.mark.parametrize("field", ["excluded_genres", "included_genres"])
@pytest.mark.parametrize("corrupt, message", [
    ("Action", "must be a list of strings"),
    (5, "must be a list of strings"),
    (["Action", 3], "must be a list of strings"),
    (["x" * 65], "at most 64 characters"),
    ([f"Genre {i}" for i in range(51)], "at most 50 genres"),
])
def test_policy_from_settings_fails_closed_on_a_corrupt_stored_genre_list(
    field: str, corrupt: Any, message: str
) -> None:
    """A hand-edited genre column is refused like a bad priority list (the
    worker logs and enters nothing; previews return CONFIG_002), never read
    as single letters nor crashing with TypeError."""
    with pytest.raises(InvalidPolicyError, match=message) as raised:
        policy_from_settings(_settings(**{field: corrupt}))
    assert raised.value.setting == field
    assert str(raised.value).startswith("Genre list setting is invalid: ")
    assert field in raised.value.problem


def test_excluded_genre_stored_as_a_string_never_lets_the_genre_through() -> None:
    """Before the check, 'Action' folded into {'a','c','t','i','o','n'} and an
    Action game became an enter candidate."""
    with pytest.raises(InvalidPolicyError):
        policy_from_settings(_settings(excluded_genres="Action", autojoin_priorities=[]))


def test_policy_override_does_not_read_the_stored_genre_lists() -> None:
    settings = _settings(excluded_genres="Action", included_genres=5)
    policy = policy_from_settings(settings, _fields(excluded_genres=["Action"]))
    assert policy.excluded_genres == frozenset({"action"})


# ----------------------------------------------------------------------------
# Explanations, kinds, registry
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("code, detail, label", [
    (ELIGIBLE, {"priority": "wishlist", "rank": 0, "lifted_by": "wishlist"}, "Joinable"),
    (ELIGIBLE, None, "Joinable"),
    (EXPIRED, {}, "Giveaway has ended"),
    (HIDDEN, {}, "Hidden"),
    (ENTERED, {}, "Already entered"),
    (UNSAFE, {"safety_score": 10}, "Flagged unsafe or borderline by the safety check"),
    (PRICE_BELOW_MIN, {"price": 5, "min_price": 10}, "Price 5P is below your minimum 10P"),
    (GENRE_EXCLUDED, {"genre": "Action"}, "Genre Action is on your excluded list"),
    (GENRE_NOT_INCLUDED, None, "No genre on your included list"),
    (NO_GAME_DATA, {}, "No Steam data cached yet; unknown data never passes the score, reviews or age filters; "
                       "checked again next cycle"),
    (NO_GAME_DATA, None, "No Steam game data cached"),
    (SCORE_BELOW_MIN, {"score": 6, "min_score": 7}, "Review score 6 is below your minimum 7"),
    (SCORE_BELOW_MIN, None, "Review score below minimum"),
    (SCORE_BELOW_MIN, {}, "Review score below minimum"),
    (REVIEWS_BELOW_MIN, {"reviews": 500, "min_reviews": 1000}, "500 reviews is below your minimum 1000"),
    (GAME_TOO_OLD, {"release_date": "2005-01-01", "max_game_age": 5},
     "Released 2005-01-01, older than your 5-year limit"),
    (GAME_TOO_OLD, {"release_date": None, "max_game_age": 5},
     "Release date unknown; games with unknown age fail your 5-year limit"),
    (BUDGET_FLOOR, {"price": 50, "points": 230, "stop_at": 200},
     "Not entered last cycle: 50P would leave 180P, below your 200P floor"),
    (BUDGET_FLOOR, {"price": "50", "points": 230, "stop_at": 200}, "Not entered last cycle: points floor"),
    (CYCLE_CAP, {"cap": 10}, "Not entered last cycle: the 10 per cycle cap was reached"),
    (POINTS_ACCUMULATING, {"points": 300, "start_at": 350},
     "Not entered last cycle: 300P is below your 350P start threshold"),
    (POINTS_ACCUMULATING, None, "Not entered last cycle: accumulating points"),
])
def test_explain(code: str, detail: dict[str, Any] | None, label: str) -> None:
    assert explain(code, detail) == label


def test_explain_null_and_unknown_codes() -> None:
    assert explain(None, None) is None
    assert explain(None, {"score": 1}) is None
    assert explain("bogus", None) == "bogus"
    assert explain("price_above_max", {"price": 5}) == "price_above_max"


@pytest.mark.parametrize("code, kind", [
    (ELIGIBLE, "enter"),
    *[(rule.code, "gate") for rule in GATES],
    *[(rule.code, "filter") for rule in FILTERS],
    (BUDGET_FLOOR, "budget"), (CYCLE_CAP, "budget"), (POINTS_ACCUMULATING, "budget"),
    (None, None), ("bogus", None),
])
def test_kind_of(code: str | None, kind: str | None) -> None:
    assert kind_of(code) == kind


def test_price_above_max_is_gone() -> None:
    assert "price_above_max" not in REASON_LABELS
    assert "price_above_max" not in RULES
    assert "price_above_max" not in str(registry_as_data())


def test_reason_labels_cover_every_rule() -> None:
    assert REASON_LABELS == {rule.code: rule.label for rule in (*GATES, *FILTERS, *OUTCOMES)}
    assert GENRE_NOT_INCLUDED in REASON_LABELS
    assert len(REASON_LABELS) == 15


def test_registry_as_data_matches_the_contract() -> None:
    assert registry_as_data() == {
        "gates": [
            {"code": "expired", "label": "Giveaway has ended"},
            {"code": "hidden", "label": "Hidden"},
            {"code": "entered", "label": "Already entered"},
            {"code": "unsafe", "label": "Flagged unsafe or borderline by the safety check"},
        ],
        "filters": [
            {"code": "price_below_min", "label": "Price below minimum", "setting": "autojoin_min_price"},
            {"code": "genre_excluded", "label": "Game genre is excluded", "setting": "excluded_genres"},
            {"code": "genre_not_included", "label": "No genre on your included list", "setting": "included_genres"},
            {"code": "no_game_data", "label": "No Steam game data cached", "setting": None},
            {"code": "score_below_min", "label": "Review score below minimum", "setting": "autojoin_min_score"},
            {"code": "reviews_below_min", "label": "Too few reviews", "setting": "autojoin_min_reviews"},
            {"code": "game_too_old", "label": "Game older than allowed (or release date unknown)",
             "setting": "autojoin_max_game_age"},
        ],
        "outcomes": [
            {"code": "eligible", "label": "Joinable"},
            {"code": "budget_floor", "label": "Not entered last cycle: points floor"},
            {"code": "cycle_cap", "label": "Not entered last cycle: per cycle cap"},
            {"code": "points_accumulating", "label": "Not entered last cycle: accumulating points"},
        ],
        "priority_types": [
            {"type": "wishlist", "label": "Wishlist", "description": "Games on your Steam wishlist",
             "exempt_from_filters": True, "params": []},
            {"type": "dlc", "label": "DLC", "description": "DLC for games you own, from the DLC listing",
             "exempt_from_filters": True, "params": []},
            {"type": "ending_soon", "label": "Ending soon",
             "description": "Giveaways ending within the threshold, soonest first", "exempt_from_filters": False,
             "params": [{"name": "threshold_minutes", "min": 5, "max": 10080, "default": 60}]},
        ],
        "limits": {"genre_max_items": 50, "genre_max_length": 64, "max_priority_items": 3},
    }


def test_registry_as_data_is_built_from_the_rule_objects() -> None:
    """Relabelling a rule object changes the served registry: no literal copy."""
    data = registry_as_data()
    assert [g["label"] for g in data["gates"]] == [rule.label for rule in GATES]
    assert [f["label"] for f in data["filters"]] == [rule.label for rule in FILTERS]
    assert [o["label"] for o in data["outcomes"]] == [rule.label for rule in OUTCOMES]
    assert [p["exempt_from_filters"] for p in data["priority_types"]] == [
        pt.exempt_from_filters for pt in PRIORITY_TYPES.values()
    ]
