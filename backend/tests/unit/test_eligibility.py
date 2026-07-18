"""Tests for autojoin eligibility evaluation.

Three layers:
1. The pure evaluator (`evaluate_eligibility`) — every reason code + precedence.
2. Behavior-equivalence — the evaluator's ELIGIBLE set must match the existing
   SQL filter (`GiveawayRepository.get_eligible`) exactly, so wiring it into the
   cycle does NOT change which giveaways get entered.
3. Persistence — a process cycle records a reason on every candidate.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.time import utcnow
from models.base import Base
from models.game import Game
from models.giveaway import Giveaway
from services.eligibility import (
    ELIGIBLE,
    ENTERED,
    EXPIRED,
    GAME_TOO_OLD,
    HIDDEN,
    NO_GAME_DATA,
    PRICE_ABOVE_MAX,
    PRICE_BELOW_MIN,
    REVIEWS_BELOW_MIN,
    SCORE_BELOW_MIN,
    EligibilityCriteria,
    evaluate_eligibility,
)
from services.game_service import GameService
from services.giveaway_service import GiveawayService

NOW = datetime(2026, 6, 17, 12, 0, 0)


def _gw(**kw):
    """A giveaway stand-in (only the attributes the evaluator reads)."""
    base = dict(
        end_time=NOW + timedelta(days=1),
        is_hidden=False,
        is_entered=False,
        is_wishlist=False,
        price=50,
        game_id=620,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _game(**kw):
    base = dict(review_score=9, total_reviews=5000, release_date="2020-01-01")
    base.update(kw)
    return SimpleNamespace(**base)


# ----------------------------------------------------------------------------
# 1. Pure evaluator
# ----------------------------------------------------------------------------

def test_eligible_when_all_criteria_pass():
    crit = EligibilityCriteria(min_price=10, min_score=7, min_reviews=1000)
    assert evaluate_eligibility(_gw(), _game(), crit, NOW) == ELIGIBLE


@pytest.mark.parametrize("end_time", [None, NOW - timedelta(hours=1)])
def test_expired(end_time):
    crit = EligibilityCriteria(min_price=10)
    assert evaluate_eligibility(_gw(end_time=end_time), _game(), crit, NOW) == EXPIRED


def test_hidden():
    crit = EligibilityCriteria(min_price=10)
    assert evaluate_eligibility(_gw(is_hidden=True), _game(), crit, NOW) == HIDDEN


def test_entered():
    crit = EligibilityCriteria(min_price=10)
    assert evaluate_eligibility(_gw(is_entered=True), _game(), crit, NOW) == ENTERED


def test_price_below_min():
    crit = EligibilityCriteria(min_price=50)
    assert evaluate_eligibility(_gw(price=49), _game(), crit, NOW) == PRICE_BELOW_MIN


def test_price_above_max():
    crit = EligibilityCriteria(min_price=10, max_price=100)
    assert evaluate_eligibility(_gw(price=150), _game(), crit, NOW) == PRICE_ABOVE_MAX


def test_no_game_data_when_criteria_need_it():
    crit = EligibilityCriteria(min_price=10, min_score=7)
    assert evaluate_eligibility(_gw(), None, crit, NOW) == NO_GAME_DATA


def test_missing_game_is_fine_when_no_game_criteria():
    # No score/reviews/age criteria → no game data required.
    crit = EligibilityCriteria(min_price=10)
    assert evaluate_eligibility(_gw(), None, crit, NOW) == ELIGIBLE


def test_score_below_min_including_unknown_zero():
    crit = EligibilityCriteria(min_price=10, min_score=7)
    assert evaluate_eligibility(_gw(), _game(review_score=6), crit, NOW) == SCORE_BELOW_MIN
    # Unknown score is stored as 0 → treated as a failure (intentional).
    assert evaluate_eligibility(_gw(), _game(review_score=0), crit, NOW) == SCORE_BELOW_MIN


def test_reviews_below_min():
    crit = EligibilityCriteria(min_price=10, min_reviews=1000)
    assert evaluate_eligibility(_gw(), _game(total_reviews=999), crit, NOW) == REVIEWS_BELOW_MIN


def test_game_too_old_and_unknown_release_date():
    crit = EligibilityCriteria(min_price=10, max_game_age=3)  # cutoff 2023-01-01
    assert evaluate_eligibility(_gw(), _game(release_date="2010-05-01"), crit, NOW) == GAME_TOO_OLD
    # Missing release date fails the age check (intentional).
    assert evaluate_eligibility(_gw(), _game(release_date=None), crit, NOW) == GAME_TOO_OLD
    # Recent enough passes.
    assert evaluate_eligibility(_gw(), _game(release_date="2024-01-01"), crit, NOW) == ELIGIBLE


def test_wishlist_bypasses_price_and_game_filters():
    # Fails every filter (price, score, reviews, age, even missing game data),
    # but is on the wishlist → eligible.
    crit = EligibilityCriteria(min_price=100, min_score=9, min_reviews=10000, max_game_age=1)
    assert evaluate_eligibility(_gw(is_wishlist=True, price=1), None, crit, NOW) == ELIGIBLE


def test_wishlist_still_respects_expired_hidden_entered():
    crit = EligibilityCriteria(min_price=10)
    assert evaluate_eligibility(
        _gw(is_wishlist=True, end_time=NOW - timedelta(hours=1)), None, crit, NOW
    ) == EXPIRED
    assert evaluate_eligibility(_gw(is_wishlist=True, is_hidden=True), None, crit, NOW) == HIDDEN
    assert evaluate_eligibility(_gw(is_wishlist=True, is_entered=True), None, crit, NOW) == ENTERED


def test_precedence_hidden_beats_price_and_score():
    crit = EligibilityCriteria(min_price=100, min_score=10)
    gw = _gw(is_hidden=True, price=1)
    assert evaluate_eligibility(gw, _game(review_score=0), crit, NOW) == HIDDEN


def test_precedence_price_beats_missing_game():
    crit = EligibilityCriteria(min_price=100, min_score=7)
    assert evaluate_eligibility(_gw(price=1), None, crit, NOW) == PRICE_BELOW_MIN


# ----------------------------------------------------------------------------
# DB-backed fixtures for layers 2 & 3
# ----------------------------------------------------------------------------

@pytest.fixture
async def test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield maker
    await engine.dispose()


async def _seed(session):
    """A mixed pool covering every reason code; returns no value."""
    # The code under test uses the real clock (utcnow()), so seed
    # relative to it — a fixed date would silently expire the whole pool.
    now = utcnow()
    future = now + timedelta(days=2)
    past = now - timedelta(days=2)

    # Games
    session.add_all([
        Game(id=1, name="Great", type="game", review_score=9, total_reviews=5000, release_date="2021-01-01"),
        Game(id=2, name="LowScore", type="game", review_score=4, total_reviews=5000, release_date="2021-01-01"),
        Game(id=3, name="FewReviews", type="game", review_score=9, total_reviews=10, release_date="2021-01-01"),
        Game(id=4, name="Old", type="game", review_score=9, total_reviews=5000, release_date="2005-01-01"),
        Game(id=5, name="Unknown", type="dlc", review_score=0, total_reviews=0, release_date=None),
    ])

    def gw(code, price=50, game_id=1, end=future, hidden=False, entered=False, wishlist=False):
        return Giveaway(
            code=code, url=f"http://x/{code}", game_name=code, price=price,
            end_time=end, game_id=game_id, is_hidden=hidden, is_entered=entered,
            is_wishlist=wishlist,
        )

    session.add_all([
        gw("good1", price=80, game_id=1),       # eligible
        gw("good2", price=60, game_id=1),       # eligible
        gw("lowscore", game_id=2),              # score below min
        gw("fewrev", game_id=3),                # reviews below min
        gw("old", game_id=4),                   # too old (only when max_game_age set)
        gw("unknown", game_id=5),               # score/reviews 0 → fails
        gw("nogame", game_id=999),              # game_id with no Game row → no_game_data
        gw("nogameid", game_id=None),           # no game_id at all → no_game_data
        gw("cheap", price=5, game_id=1),        # price below min (min_price=10)
        gw("hidden", game_id=1, hidden=True),   # hidden
        gw("entered", game_id=1, entered=True), # entered (excluded from candidates)
        gw("expired", game_id=1, end=past),     # expired (excluded by active filter)
        # Wishlist rows: bypass price/game filters even with bad or missing data
        gw("wishbad", price=1, game_id=2, wishlist=True),      # low price + low score → still eligible
        gw("wishnogame", game_id=None, wishlist=True),         # no game data → still eligible
        gw("wishhidden", game_id=1, hidden=True, wishlist=True),  # hidden beats wishlist
    ])
    await session.commit()


def _service(session):
    game_service = GameService(session=session, steam_client=MagicMock())
    return GiveawayService(session, MagicMock(), game_service)


# ----------------------------------------------------------------------------
# 2. Behavior-equivalence: evaluator ELIGIBLE set == SQL get_eligible
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("crit_kwargs", [
    dict(min_price=10, min_score=7, min_reviews=1000),                 # defaults
    dict(min_price=10, min_score=7, min_reviews=1000, max_game_age=5), # + age
    dict(min_price=10),                                                # no game criteria
    dict(min_price=10, max_price=70, min_score=7, min_reviews=1000),   # + max price
    dict(min_price=0, min_score=0, min_reviews=0),                     # zero thresholds
])
@pytest.mark.asyncio
async def test_evaluator_matches_sql_get_eligible(test_db, crit_kwargs):
    async with test_db() as session:
        await _seed(session)
        service = _service(session)

        sql_eligible = await service.giveaway_repo.get_eligible(**crit_kwargs)
        sql_codes = {g.code for g in sql_eligible}
        # Guard against vacuous equivalence: every param set is chosen so the
        # seeded pool yields at least one eligible giveaway.
        assert sql_codes, f"seed produced no SQL-eligible giveaways for {crit_kwargs}"

        criteria = EligibilityCriteria(**{
            "min_price": crit_kwargs.get("min_price", 0),
            "max_price": crit_kwargs.get("max_price"),
            "min_score": crit_kwargs.get("min_score"),
            "min_reviews": crit_kwargs.get("min_reviews"),
            "max_game_age": crit_kwargs.get("max_game_age"),
        })
        evaluated = await service.evaluate_and_get_eligible(criteria)
        eval_codes = {g.code for g in evaluated}

        assert eval_codes == sql_codes, f"mismatch for {crit_kwargs}"
        # Wishlist rows bypass the filters, so they are always in the set.
        assert {"wishbad", "wishnogame"} <= eval_codes
        assert "wishhidden" not in eval_codes
        # Ordering: wishlist first, then price descending within each group.
        keys = [(not g.is_wishlist, -g.price) for g in evaluated]
        assert keys == sorted(keys)


# ----------------------------------------------------------------------------
# 3. Persistence: every candidate gets a recorded reason
# ----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reasons_persisted_for_all_candidates(test_db):
    async with test_db() as session:
        await _seed(session)
        service = _service(session)

        criteria = EligibilityCriteria(min_price=10, min_score=7, min_reviews=1000)
        await service.evaluate_and_get_eligible(criteria)

        # Reload and check stored reasons (entered/expired are not candidates).
        reasons = {
            g.code: g.eligibility_reason
            for g in await service.giveaway_repo.get_all()
        }

        assert reasons["good1"] == ELIGIBLE
        assert reasons["good2"] == ELIGIBLE
        assert reasons["lowscore"] == SCORE_BELOW_MIN
        assert reasons["fewrev"] == REVIEWS_BELOW_MIN
        assert reasons["unknown"] == SCORE_BELOW_MIN
        assert reasons["nogame"] == NO_GAME_DATA
        assert reasons["nogameid"] == NO_GAME_DATA
        assert reasons["cheap"] == PRICE_BELOW_MIN
        assert reasons["hidden"] == HIDDEN
        # 'old' is only too-old when max_game_age is set; here it's eligible.
        assert reasons["old"] == ELIGIBLE
        # Entered and expired giveaways aren't in the active candidate pool.
        assert reasons["entered"] is None
        assert reasons["expired"] is None

        # checked_at recorded for everything that was evaluated.
        checked = {
            g.code: g.eligibility_checked_at
            for g in await service.giveaway_repo.get_all()
        }
        assert checked["good1"] is not None
        assert checked["entered"] is None
