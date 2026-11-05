"""Golden parity guard for the auto-join engine (severity high).

The ordered enter lists below were produced by the engine this redesign
replaced (``evaluate_eligibility`` + ``priority_sort_key`` from
backend/src/services/eligibility.py at origin/master 1ab359a, copied verbatim
into a test-only oracle, run, then deleted). The new registry engine must
produce exactly the same giveaways in exactly the same order for:

- the 15 criteria sets of the former SQL-parity test over its seeded pool;
- a priority pool where rows match several priority types (wishlist + DLC,
  wishlist ending soon, ...), at four ending-soon thresholds;

each crossed with the 8 combinations of the old wishlist, DLC and ending-soon
flags, mapped to priority lists in the migration's order (wishlist, dlc,
ending_soon; a disabled flag is an absent item). The include list stays
empty, so it must be inert. The per-cycle cap and the budget are not part of
this test (the cap semantics changed on purpose; see test_eligibility.py).

Flag keys are "<wishlist><dlc><ending_soon>" with 1 = enabled.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.time import utcnow
from models.base import Base
from models.game import Game
from models.giveaway import Giveaway
from repositories.game import GameRepository
from repositories.giveaway import GiveawayRepository
from services.eligibility import AutoJoinPolicy, PriorityItem, decide, order_candidates

CRIT_PARAMS: list[dict[str, Any]] = [
    dict(min_price=10, min_score=7, min_reviews=1000),
    dict(min_price=10, min_score=7, min_reviews=1000, max_game_age=5),
    dict(min_price=10),
    dict(min_price=0, min_score=0, min_reviews=0),
    dict(min_price=10, min_score=7, min_reviews=1000),
    dict(min_price=10, min_score=7, min_reviews=1000),
    dict(min_price=10, min_score=7, min_reviews=1000),
    dict(min_price=10, min_score=7, min_reviews=1000, ending_soon_threshold_minutes=10080),
    dict(min_price=10, min_score=7, min_reviews=1000, excluded_genres=["ACTION"]),
    dict(min_price=10, excluded_genres=["action"]),
    dict(min_price=10, min_score=0, min_reviews=0, excluded_genres=["indie"]),
    dict(min_price=10, excluded_genres=["Racing", " Indie ", ""], max_game_age=5),
    dict(min_price=10, excluded_genres=["ACCIÓN"]),
    dict(min_price=10, excluded_genres=["ACCIóN"]),
    dict(min_price=10, excluded_genres=[]),
]
FLAG_MASKS = [f"{w}{d}{e}" for w in "01" for d in "01" for e in "01"]
PRIORITY_POOL_THRESHOLDS = [5, 30, 60, 10080]


def _priorities(mask: str, threshold: int) -> tuple[PriorityItem, ...]:
    """The priority list the migration builds from the old three flags."""
    items: list[PriorityItem] = []
    if mask[0] == "1":
        items.append(PriorityItem("wishlist"))
    if mask[1] == "1":
        items.append(PriorityItem("dlc"))
    if mask[2] == "1":
        items.append(PriorityItem("ending_soon", threshold_minutes=threshold))
    return tuple(items)


async def _seed(session: AsyncSession) -> None:
    """The mixed pool of the former SQL-parity test (one row per reason code)."""
    now = utcnow()
    future = now + timedelta(days=2)
    past = now - timedelta(days=2)
    session.add_all([
        Game(id=1, name="Great", type="game", review_score=9, total_reviews=5000, release_date="2021-01-01",
             genres=["Puzzle"]),
        Game(id=2, name="LowScore", type="game", review_score=4, total_reviews=5000, release_date="2021-01-01"),
        Game(id=3, name="FewReviews", type="game", review_score=9, total_reviews=10, release_date="2021-01-01"),
        Game(id=4, name="Old", type="game", review_score=9, total_reviews=5000, release_date="2005-01-01"),
        Game(id=5, name="Unknown", type="dlc", review_score=0, total_reviews=0, release_date=None),
        Game(id=6, name="ActionIndie", type="game", review_score=9, total_reviews=5000,
             release_date="2024-01-01", genres=["Action", "Indie"]),
        Game(id=7, name="NoGenres", type="game", review_score=9, total_reviews=5000,
             release_date="2024-01-01", genres=[]),
        Game(id=8, name="Unfetched", type="game", review_score=9, total_reviews=5000,
             release_date="2024-01-01", genres=None),
        Game(id=9, name="Accented", type="game", review_score=9, total_reviews=5000,
             release_date="2024-01-01", genres=["Acción"]),
    ])

    def gw(code, price=50, game_id=1, end=future, hidden=False, entered=False,
           wishlist=False, dlc=False, safe=None):
        return Giveaway(
            code=code, url=f"http://x/{code}", game_name=code, price=price,
            end_time=end, game_id=game_id, is_hidden=hidden, is_entered=entered,
            is_wishlist=wishlist, is_dlc=dlc, is_safe=safe,
        )

    session.add_all([
        gw("good1", price=80, game_id=1),
        gw("good2", price=60, game_id=1),
        gw("lowscore", game_id=2),
        gw("fewrev", game_id=3),
        gw("old", game_id=4),
        gw("unknown", game_id=5),
        gw("nogame", game_id=999),
        gw("nogameid", game_id=None),
        gw("cheap", price=5, game_id=1),
        gw("hidden", game_id=1, hidden=True),
        gw("entered", game_id=1, entered=True),
        gw("expired", game_id=1, end=past),
        gw("wishbad", price=1, game_id=2, wishlist=True),
        gw("wishnogame", game_id=None, wishlist=True),
        gw("wishhidden", game_id=1, hidden=True, wishlist=True),
        gw("dlcbad", price=1, game_id=2, dlc=True),
        gw("unsafegw", price=80, game_id=1, safe=False),
        gw("wishunsafe", price=80, game_id=1, wishlist=True, safe=False),
        gw("safegw", price=80, game_id=1, safe=True),
        gw("genrebad", price=65, game_id=6),
        gw("genreempty", price=65, game_id=7),
        gw("genrenull", price=65, game_id=8),
        gw("genreaccent", price=65, game_id=9),
        gw("wishgenre", price=65, game_id=6, wishlist=True),
        gw("dlcgenre", price=65, game_id=6, dlc=True),
    ])
    await session.commit()


@pytest.fixture
async def seeded_pool() -> tuple[list[Giveaway], dict[int, Game]]:
    """The seeded candidate pool (price descending, ties by id) and its games."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        await _seed(session)
        pool = await GiveawayRepository(session).get_active_unentered()
        pool.sort(key=lambda g: (-g.price, g.id))
        games = await GameRepository(session).get_by_ids([g.game_id for g in pool if g.game_id])
    await engine.dispose()
    return pool, games


def _priority_pool(now: datetime) -> list[Any]:
    """Wishlist/DLC/ending-soon rows (some matching several types), price descending."""
    t = timedelta

    def g(code: str, price: int, end: datetime, wishlist: bool = False, dlc: bool = False) -> SimpleNamespace:
        return SimpleNamespace(code=code, price=price, end_time=end, is_hidden=False, is_entered=False,
                               is_safe=None, safety_score=None, is_wishlist=wishlist, is_dlc=dlc, game_id=None)
    return [
        g("far", 900, now + t(days=3)),
        g("wishdlc_soon", 700, now + t(minutes=20), wishlist=True, dlc=True),
        g("past_thr", 500, now + t(minutes=61)),
        g("wishdlc", 400, now + t(days=3), wishlist=True, dlc=True),
        g("noend_far", 300, now + t(days=9)),
        g("wish2", 40, now + t(days=3), wishlist=True),
        g("dlc2", 30, now + t(days=3), dlc=True),
        g("soon5", 20, now + t(minutes=5)),
        g("dlc", 15, now + t(minutes=10), dlc=True),
        g("at_thr", 10, now + t(minutes=60)),
        g("wish", 5, now + t(minutes=10), wishlist=True),
        g("wishdlc_cheap", 2, now + t(minutes=30), wishlist=True, dlc=True),
    ]


GOLDEN_SEEDED: dict[tuple[int, str], list[str]] = {
    (0, "000"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "old",
    ],
    (0, "001"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "old",
    ],
    (0, "010"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "old",
    ],
    (0, "011"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "old",
    ],
    (0, "100"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "old",
    ],
    (0, "101"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "old",
    ],
    (0, "110"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "old",
    ],
    (0, "111"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "old",
    ],
    (1, "000"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
    ],
    (1, "001"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
    ],
    (1, "010"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2",
    ],
    (1, "011"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2",
    ],
    (1, "100"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2",
    ],
    (1, "101"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2",
    ],
    (1, "110"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2",
    ],
    (1, "111"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2",
    ],
    (2, "000"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (2, "001"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (2, "010"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (2, "011"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (2, "100"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (2, "101"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (2, "110"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (2, "111"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (3, "000"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "lowscore", "fewrev", "old", "unknown", "cheap", "wishbad", "dlcbad",
    ],
    (3, "001"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "lowscore", "fewrev", "old", "unknown", "cheap", "wishbad", "dlcbad",
    ],
    (3, "010"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "lowscore", "fewrev", "old", "unknown", "cheap", "wishbad",
    ],
    (3, "011"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "lowscore", "fewrev", "old", "unknown", "cheap", "wishbad",
    ],
    (3, "100"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "lowscore", "fewrev", "old", "unknown", "cheap", "dlcbad",
    ],
    (3, "101"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "lowscore", "fewrev", "old", "unknown", "cheap", "dlcbad",
    ],
    (3, "110"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "lowscore", "fewrev", "old", "unknown", "cheap",
    ],
    (3, "111"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "lowscore", "fewrev", "old", "unknown", "cheap",
    ],
    (4, "000"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "old",
    ],
    (4, "001"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "old",
    ],
    (4, "010"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "old",
    ],
    (4, "011"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "old",
    ],
    (4, "100"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "old",
    ],
    (4, "101"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "old",
    ],
    (4, "110"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "old",
    ],
    (4, "111"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "old",
    ],
    (5, "000"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "old",
    ],
    (5, "001"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "old",
    ],
    (5, "010"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "old",
    ],
    (5, "011"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "old",
    ],
    (5, "100"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "old",
    ],
    (5, "101"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "old",
    ],
    (5, "110"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "old",
    ],
    (5, "111"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "old",
    ],
    (6, "000"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "old",
    ],
    (6, "001"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "old",
    ],
    (6, "010"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "old",
    ],
    (6, "011"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "old",
    ],
    (6, "100"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "old",
    ],
    (6, "101"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "old",
    ],
    (6, "110"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "old",
    ],
    (6, "111"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "old",
    ],
    (7, "000"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "old",
    ],
    (7, "001"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "old",
    ],
    (7, "010"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "old",
    ],
    (7, "011"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "old",
    ],
    (7, "100"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "old",
    ],
    (7, "101"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "old",
    ],
    (7, "110"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "old",
    ],
    (7, "111"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "old",
    ],
    (8, "000"): ["good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2", "old"],
    (8, "001"): ["good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2", "old"],
    (8, "010"): ["dlcgenre", "dlcbad", "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2", "old"],
    (8, "011"): ["dlcgenre", "dlcbad", "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2", "old"],
    (8, "100"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2",
        "old",
    ],
    (8, "101"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2",
        "old",
    ],
    (8, "110"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genreempty", "genrenull",
        "genreaccent", "good2", "old",
    ],
    (8, "111"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genreempty", "genrenull",
        "genreaccent", "good2", "old",
    ],
    (9, "000"): [
        "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2", "lowscore", "fewrev", "old", "unknown",
        "nogame", "nogameid", "wishnogame",
    ],
    (9, "001"): [
        "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2", "lowscore", "fewrev", "old", "unknown",
        "nogame", "nogameid", "wishnogame",
    ],
    (9, "010"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2", "lowscore",
        "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (9, "011"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2", "lowscore",
        "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (9, "100"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2",
        "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (9, "101"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2",
        "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (9, "110"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genreempty", "genrenull",
        "genreaccent", "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (9, "111"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genreempty", "genrenull",
        "genreaccent", "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (10, "000"): [
        "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2", "lowscore", "fewrev", "old", "unknown",
    ],
    (10, "001"): [
        "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2", "lowscore", "fewrev", "old", "unknown",
    ],
    (10, "010"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2", "lowscore",
        "fewrev", "old", "unknown",
    ],
    (10, "011"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2", "lowscore",
        "fewrev", "old", "unknown",
    ],
    (10, "100"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2",
        "lowscore", "fewrev", "old", "unknown",
    ],
    (10, "101"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2",
        "lowscore", "fewrev", "old", "unknown",
    ],
    (10, "110"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genreempty", "genrenull",
        "genreaccent", "good2", "lowscore", "fewrev", "old", "unknown",
    ],
    (10, "111"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genreempty", "genrenull",
        "genreaccent", "good2", "lowscore", "fewrev", "old", "unknown",
    ],
    (11, "000"): ["good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2", "lowscore", "fewrev"],
    (11, "001"): ["good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2", "lowscore", "fewrev"],
    (11, "010"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2", "lowscore",
        "fewrev",
    ],
    (11, "011"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2", "lowscore",
        "fewrev",
    ],
    (11, "100"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2",
        "lowscore", "fewrev",
    ],
    (11, "101"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genreempty", "genrenull", "genreaccent", "good2",
        "lowscore", "fewrev",
    ],
    (11, "110"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genreempty", "genrenull",
        "genreaccent", "good2", "lowscore", "fewrev",
    ],
    (11, "111"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genreempty", "genrenull",
        "genreaccent", "good2", "lowscore", "fewrev",
    ],
    (12, "000"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (12, "001"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (12, "010"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (12, "011"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (12, "100"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (12, "101"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (12, "110"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (12, "111"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (13, "000"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "wishgenre", "dlcgenre", "good2", "lowscore",
        "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (13, "001"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "wishgenre", "dlcgenre", "good2", "lowscore",
        "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (13, "010"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "wishgenre", "good2",
        "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (13, "011"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "wishgenre", "good2",
        "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (13, "100"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "dlcgenre",
        "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (13, "101"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "dlcgenre",
        "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (13, "110"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (13, "111"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (14, "000"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (14, "001"): [
        "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre", "dlcgenre", "good2",
        "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (14, "010"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (14, "011"): [
        "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent", "wishgenre",
        "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid", "wishnogame",
    ],
    (14, "100"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (14, "101"): [
        "wishgenre", "wishnogame", "wishbad", "good1", "safegw", "genrebad", "genreempty", "genrenull", "genreaccent",
        "dlcgenre", "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (14, "110"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
    (14, "111"): [
        "wishgenre", "wishnogame", "wishbad", "dlcgenre", "dlcbad", "good1", "safegw", "genrebad", "genreempty",
        "genrenull", "genreaccent", "good2", "lowscore", "fewrev", "old", "unknown", "nogame", "nogameid",
    ],
}

GOLDEN_PRIORITY_POOL: dict[tuple[int, str], list[str]] = {
    (5, "000"): [
        "far", "wishdlc_soon", "past_thr", "wishdlc", "noend_far", "wish2", "dlc2", "soon5", "dlc", "at_thr", "wish",
        "wishdlc_cheap",
    ],
    (5, "001"): [
        "soon5", "far", "wishdlc_soon", "past_thr", "wishdlc", "noend_far", "wish2", "dlc2", "dlc", "at_thr", "wish",
        "wishdlc_cheap",
    ],
    (5, "010"): [
        "wishdlc_soon", "wishdlc", "dlc2", "dlc", "wishdlc_cheap", "far", "past_thr", "noend_far", "wish2", "soon5",
        "at_thr", "wish",
    ],
    (5, "011"): [
        "wishdlc_soon", "wishdlc", "dlc2", "dlc", "wishdlc_cheap", "soon5", "far", "past_thr", "noend_far", "wish2",
        "at_thr", "wish",
    ],
    (5, "100"): [
        "wishdlc_soon", "wishdlc", "wish2", "wish", "wishdlc_cheap", "far", "past_thr", "noend_far", "dlc2", "soon5",
        "dlc", "at_thr",
    ],
    (5, "101"): [
        "wishdlc_soon", "wishdlc", "wish2", "wish", "wishdlc_cheap", "soon5", "far", "past_thr", "noend_far", "dlc2",
        "dlc", "at_thr",
    ],
    (5, "110"): [
        "wishdlc_soon", "wishdlc", "wishdlc_cheap", "wish2", "wish", "dlc2", "dlc", "far", "past_thr", "noend_far",
        "soon5", "at_thr",
    ],
    (5, "111"): [
        "wishdlc_soon", "wishdlc", "wishdlc_cheap", "wish2", "wish", "dlc2", "dlc", "soon5", "far", "past_thr",
        "noend_far", "at_thr",
    ],
    (30, "000"): [
        "far", "wishdlc_soon", "past_thr", "wishdlc", "noend_far", "wish2", "dlc2", "soon5", "dlc", "at_thr", "wish",
        "wishdlc_cheap",
    ],
    (30, "001"): [
        "soon5", "dlc", "wish", "wishdlc_soon", "wishdlc_cheap", "far", "past_thr", "wishdlc", "noend_far", "wish2",
        "dlc2", "at_thr",
    ],
    (30, "010"): [
        "wishdlc_soon", "wishdlc", "dlc2", "dlc", "wishdlc_cheap", "far", "past_thr", "noend_far", "wish2", "soon5",
        "at_thr", "wish",
    ],
    (30, "011"): [
        "wishdlc_soon", "wishdlc", "dlc2", "dlc", "wishdlc_cheap", "soon5", "wish", "far", "past_thr", "noend_far",
        "wish2", "at_thr",
    ],
    (30, "100"): [
        "wishdlc_soon", "wishdlc", "wish2", "wish", "wishdlc_cheap", "far", "past_thr", "noend_far", "dlc2", "soon5",
        "dlc", "at_thr",
    ],
    (30, "101"): [
        "wishdlc_soon", "wishdlc", "wish2", "wish", "wishdlc_cheap", "soon5", "dlc", "far", "past_thr", "noend_far",
        "dlc2", "at_thr",
    ],
    (30, "110"): [
        "wishdlc_soon", "wishdlc", "wishdlc_cheap", "wish2", "wish", "dlc2", "dlc", "far", "past_thr", "noend_far",
        "soon5", "at_thr",
    ],
    (30, "111"): [
        "wishdlc_soon", "wishdlc", "wishdlc_cheap", "wish2", "wish", "dlc2", "dlc", "soon5", "far", "past_thr",
        "noend_far", "at_thr",
    ],
    (60, "000"): [
        "far", "wishdlc_soon", "past_thr", "wishdlc", "noend_far", "wish2", "dlc2", "soon5", "dlc", "at_thr", "wish",
        "wishdlc_cheap",
    ],
    (60, "001"): [
        "soon5", "dlc", "wish", "wishdlc_soon", "wishdlc_cheap", "at_thr", "far", "past_thr", "wishdlc", "noend_far",
        "wish2", "dlc2",
    ],
    (60, "010"): [
        "wishdlc_soon", "wishdlc", "dlc2", "dlc", "wishdlc_cheap", "far", "past_thr", "noend_far", "wish2", "soon5",
        "at_thr", "wish",
    ],
    (60, "011"): [
        "wishdlc_soon", "wishdlc", "dlc2", "dlc", "wishdlc_cheap", "soon5", "wish", "at_thr", "far", "past_thr",
        "noend_far", "wish2",
    ],
    (60, "100"): [
        "wishdlc_soon", "wishdlc", "wish2", "wish", "wishdlc_cheap", "far", "past_thr", "noend_far", "dlc2", "soon5",
        "dlc", "at_thr",
    ],
    (60, "101"): [
        "wishdlc_soon", "wishdlc", "wish2", "wish", "wishdlc_cheap", "soon5", "dlc", "at_thr", "far", "past_thr",
        "noend_far", "dlc2",
    ],
    (60, "110"): [
        "wishdlc_soon", "wishdlc", "wishdlc_cheap", "wish2", "wish", "dlc2", "dlc", "far", "past_thr", "noend_far",
        "soon5", "at_thr",
    ],
    (60, "111"): [
        "wishdlc_soon", "wishdlc", "wishdlc_cheap", "wish2", "wish", "dlc2", "dlc", "soon5", "at_thr", "far",
        "past_thr", "noend_far",
    ],
    (10080, "000"): [
        "far", "wishdlc_soon", "past_thr", "wishdlc", "noend_far", "wish2", "dlc2", "soon5", "dlc", "at_thr", "wish",
        "wishdlc_cheap",
    ],
    (10080, "001"): [
        "soon5", "dlc", "wish", "wishdlc_soon", "wishdlc_cheap", "at_thr", "past_thr", "far", "wishdlc", "wish2",
        "dlc2", "noend_far",
    ],
    (10080, "010"): [
        "wishdlc_soon", "wishdlc", "dlc2", "dlc", "wishdlc_cheap", "far", "past_thr", "noend_far", "wish2", "soon5",
        "at_thr", "wish",
    ],
    (10080, "011"): [
        "wishdlc_soon", "wishdlc", "dlc2", "dlc", "wishdlc_cheap", "soon5", "wish", "at_thr", "past_thr", "far",
        "wish2", "noend_far",
    ],
    (10080, "100"): [
        "wishdlc_soon", "wishdlc", "wish2", "wish", "wishdlc_cheap", "far", "past_thr", "noend_far", "dlc2", "soon5",
        "dlc", "at_thr",
    ],
    (10080, "101"): [
        "wishdlc_soon", "wishdlc", "wish2", "wish", "wishdlc_cheap", "soon5", "dlc", "at_thr", "past_thr", "far",
        "dlc2", "noend_far",
    ],
    (10080, "110"): [
        "wishdlc_soon", "wishdlc", "wishdlc_cheap", "wish2", "wish", "dlc2", "dlc", "far", "past_thr", "noend_far",
        "soon5", "at_thr",
    ],
    (10080, "111"): [
        "wishdlc_soon", "wishdlc", "wishdlc_cheap", "wish2", "wish", "dlc2", "dlc", "soon5", "at_thr", "past_thr",
        "far", "noend_far",
    ],
}


def test_golden_tables_cover_every_combination() -> None:
    assert set(GOLDEN_SEEDED) == {(i, m) for i in range(len(CRIT_PARAMS)) for m in FLAG_MASKS}
    assert set(GOLDEN_PRIORITY_POOL) == {(t, m) for t in PRIORITY_POOL_THRESHOLDS for m in FLAG_MASKS}


@pytest.mark.parametrize("mask", FLAG_MASKS)
@pytest.mark.parametrize("index", range(len(CRIT_PARAMS)))
def test_seeded_pool_matches_golden(
    seeded_pool: tuple[list[Giveaway], dict[int, Game]], index: int, mask: str
) -> None:
    pool, games = seeded_pool
    params = CRIT_PARAMS[index]
    threshold = params.get("ending_soon_threshold_minutes", 60)
    now = utcnow()
    policy = AutoJoinPolicy(
        min_price=params.get("min_price", 0),
        min_score=params.get("min_score"),
        min_reviews=params.get("min_reviews"),
        max_game_age=params.get("max_game_age"),
        excluded_genres=frozenset(params.get("excluded_genres", [])),
        included_genres=frozenset(),
        priorities=_priorities(mask, threshold),
    )

    decided = [(g, decide(g, games.get(g.game_id) if g.game_id else None, policy, now)) for g in pool]
    ordered = [g.code for g, _ in order_candidates(decided, policy, now)]

    assert ordered == GOLDEN_SEEDED[(index, mask)]


@pytest.mark.parametrize("mask", FLAG_MASKS)
@pytest.mark.parametrize("threshold", PRIORITY_POOL_THRESHOLDS)
def test_priority_pool_matches_golden(threshold: int, mask: str) -> None:
    now = utcnow()
    pool = _priority_pool(now)
    policy = AutoJoinPolicy(priorities=_priorities(mask, threshold))

    decided = [(g, decide(g, None, policy, now)) for g in pool]
    ordered = [g.code for g, _ in order_candidates(decided, policy, now)]

    assert ordered == GOLDEN_PRIORITY_POOL[(threshold, mask)]
