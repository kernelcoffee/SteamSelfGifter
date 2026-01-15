"""Unit tests for game API schemas."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from api.schemas.game import (
    GameBase,
    GameResponse,
    GameList,
    GameFilter,
    GameRefreshResponse,
    GameStats,
)


def test_game_base():
    """Test GameBase creation."""
    game = GameBase(
        id=620,
        name="Portal 2",
        type="game"
    )

    assert game.id == 620
    assert game.name == "Portal 2"
    assert game.type == "game"
    assert game.is_bundle is False  # default


def test_game_base_with_reviews():
    """Test GameBase with review data."""
    game = GameBase(
        id=620,
        name="Portal 2",
        type="game",
        review_score=9,
        total_positive=150000,
        total_negative=5000,
        total_reviews=155000
    )

    assert game.review_score == 9
    assert game.total_positive == 150000
    assert game.total_reviews == 155000


def test_game_base_with_bundle():
    """Test GameBase for bundle type."""
    game = GameBase(
        id=1000,
        name="Game Bundle",
        type="bundle",
        is_bundle=True,
        bundle_content=[620, 400]
    )

    assert game.is_bundle is True
    assert game.bundle_content == [620, 400]


def test_game_base_with_dlc():
    """Test GameBase for DLC type."""
    game = GameBase(
        id=123,
        name="Portal 2 DLC",
        type="dlc",
        game_id=620
    )

    assert game.type == "dlc"
    assert game.game_id == 620


def test_game_base_validates_review_score():
    """Test GameBase validates review_score range."""
    # Valid values
    GameBase(id=1, name="Game", type="game", review_score=0)
    GameBase(id=1, name="Game", type="game", review_score=10)

    # Invalid: too high
    with pytest.raises(ValidationError):
        GameBase(id=1, name="Game", type="game", review_score=11)


def test_game_base_validates_negative_reviews():
    """Test GameBase rejects negative review counts."""
    with pytest.raises(ValidationError):
        GameBase(id=1, name="Game", type="game", total_positive=-100)

    with pytest.raises(ValidationError):
        GameBase(id=1, name="Game", type="game", total_reviews=-10)


def test_game_response():
    """Test GameResponse."""
    game = GameResponse(
        id=620,
        name="Portal 2",
        type="game",
        review_score=9,
        last_refreshed_at=datetime.utcnow()
    )

    assert game.id == 620
    assert game.last_refreshed_at is not None


def test_game_list():
    """Test GameList."""
    game1 = GameResponse(id=620, name="Portal 2", type="game")
    game2 = GameResponse(id=400, name="Portal", type="game")

    game_list = GameList(games=[game1, game2])

    assert len(game_list.games) == 2


def test_game_filter():
    """Test GameFilter."""
    filters = GameFilter(
        type="game",
        min_score=7,
        min_reviews=1000,
        search="Portal"
    )

    assert filters.type == "game"
    assert filters.min_score == 7
    assert filters.min_reviews == 1000
    assert filters.search == "Portal"


def test_game_filter_all_optional():
    """Test GameFilter with all fields optional."""
    filters = GameFilter()

    assert filters.type is None
    assert filters.min_score is None
    assert filters.min_reviews is None
    assert filters.search is None


def test_game_filter_validates_min_score():
    """Test GameFilter validates min_score range."""
    # Valid
    GameFilter(min_score=0)
    GameFilter(min_score=10)

    # Invalid: too high
    with pytest.raises(ValidationError):
        GameFilter(min_score=11)


def test_game_refresh_response():
    """Test GameRefreshResponse."""
    response = GameRefreshResponse(
        refreshed=True,
        message="Game data refreshed successfully",
        last_refreshed_at=datetime.utcnow()
    )

    assert response.refreshed is True
    assert response.message == "Game data refreshed successfully"
    assert response.last_refreshed_at is not None


def test_game_stats():
    """Test GameStats."""
    stats = GameStats(
        total=500,
        games=450,
        dlc=40,
        bundles=10
    )

    assert stats.total == 500
    assert stats.games == 450
    assert stats.dlc == 40
    assert stats.bundles == 10


def test_game_response_orm_mode():
    """Test GameResponse has ORM mode enabled."""
    assert GameResponse.model_config.get("from_attributes") is True
