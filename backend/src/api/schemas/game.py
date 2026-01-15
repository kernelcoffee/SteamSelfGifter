"""API schemas for game endpoints.

This module provides Pydantic schemas for game-related
API requests and responses.
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class GameBase(BaseModel):
    """
    Base game schema with common fields.

    This serves as the base for other game schemas.
    """

    id: int = Field(
        ...,
        description="Steam App ID",
        examples=[620],
    )
    name: str = Field(
        ...,
        description="Game name",
        min_length=1,
        examples=["Portal 2"],
    )
    type: str = Field(
        ...,
        description="Type (game, dlc, bundle, etc.)",
        examples=["game"],
    )
    release_date: Optional[str] = Field(
        default=None,
        description="Release date string",
        examples=["Apr 18, 2011"],
    )
    review_score: Optional[int] = Field(
        default=None,
        description="Steam review score (0-10)",
        ge=0,
        le=10,
        examples=[9],
    )
    total_positive: Optional[int] = Field(
        default=None,
        description="Number of positive reviews",
        ge=0,
        examples=[150000],
    )
    total_negative: Optional[int] = Field(
        default=None,
        description="Number of negative reviews",
        ge=0,
        examples=[5000],
    )
    total_reviews: Optional[int] = Field(
        default=None,
        description="Total number of reviews",
        ge=0,
        examples=[155000],
    )
    is_bundle: bool = Field(
        default=False,
        description="Whether this is a bundle",
        examples=[False],
    )
    bundle_content: Optional[list[int]] = Field(
        default=None,
        description="List of App IDs in bundle (if is_bundle)",
        examples=[[620, 400]],
    )
    game_id: Optional[int] = Field(
        default=None,
        description="Parent game ID (for DLC)",
        examples=[620],
    )
    description: Optional[str] = Field(
        default=None,
        description="Game description",
        examples=["Portal 2 is a puzzle-platform game..."],
    )
    price: Optional[int] = Field(
        default=None,
        description="Price in cents (USD)",
        ge=0,
        examples=[1999],
    )


class GameResponse(GameBase):
    """
    Game response schema.

    Extends GameBase with metadata fields.

    Example:
        >>> game = GameResponse(
        ...     id=620,
        ...     name="Portal 2",
        ...     type="game",
        ...     review_score=9,
        ...     last_refreshed_at=datetime.utcnow()
        ... )
    """

    last_refreshed_at: Optional[datetime] = Field(
        default=None,
        description="Last time game data was refreshed from Steam",
        examples=["2025-10-14T12:00:00"],
    )

    model_config = {
        "from_attributes": True,  # Enable ORM mode
        "json_schema_extra": {
            "examples": [
                {
                    "id": 620,
                    "name": "Portal 2",
                    "type": "game",
                    "release_date": "Apr 18, 2011",
                    "review_score": 9,
                    "total_positive": 150000,
                    "total_negative": 5000,
                    "total_reviews": 155000,
                    "is_bundle": False,
                    "bundle_content": None,
                    "game_id": None,
                    "description": "Portal 2 is a puzzle-platform game...",
                    "price": 1999,
                    "last_refreshed_at": "2025-10-14T12:00:00",
                }
            ]
        },
    }


class GameList(BaseModel):
    """
    Schema for list of games.

    Example:
        >>> games = GameList(games=[...])
    """

    games: list[GameResponse] = Field(
        ...,
        description="List of games",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "games": [
                        {
                            "id": 620,
                            "name": "Portal 2",
                            "type": "game",
                            "review_score": 9,
                            "total_reviews": 155000,
                        }
                    ]
                }
            ]
        }
    }


class GameFilter(BaseModel):
    """
    Query parameters for filtering games.

    Example:
        >>> filters = GameFilter(
        ...     type="game",
        ...     min_score=7,
        ...     search="Portal"
        ... )
    """

    type: Optional[str] = Field(
        default=None,
        description="Filter by type (game, dlc, bundle)",
        examples=["game"],
    )
    min_score: Optional[int] = Field(
        default=None,
        description="Minimum review score (0-10)",
        ge=0,
        le=10,
        examples=[7],
    )
    min_reviews: Optional[int] = Field(
        default=None,
        description="Minimum number of reviews",
        ge=0,
        examples=[1000],
    )
    search: Optional[str] = Field(
        default=None,
        description="Search by game name",
        examples=["Portal"],
    )


class GameRefreshResponse(BaseModel):
    """
    Response schema for game refresh operation.

    Example:
        >>> response = GameRefreshResponse(
        ...     refreshed=True,
        ...     message="Game data refreshed successfully",
        ...     last_refreshed_at=datetime.utcnow()
        ... )
    """

    refreshed: bool = Field(
        ...,
        description="Whether refresh was successful",
        examples=[True],
    )
    message: str = Field(
        ...,
        description="Refresh result message",
        examples=["Game data refreshed successfully"],
    )
    last_refreshed_at: Optional[datetime] = Field(
        default=None,
        description="When game data was last refreshed",
        examples=["2025-10-14T12:00:00"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "refreshed": True,
                    "message": "Game data refreshed successfully",
                    "last_refreshed_at": "2025-10-14T12:00:00",
                }
            ]
        }
    }


class GameStats(BaseModel):
    """
    Statistics about games.

    Example:
        >>> stats = GameStats(
        ...     total=500,
        ...     games=450,
        ...     dlc=40,
        ...     bundles=10
        ... )
    """

    total: int = Field(
        ...,
        description="Total number of games in database",
        ge=0,
        examples=[500],
    )
    games: int = Field(
        ...,
        description="Number of games (type=game)",
        ge=0,
        examples=[450],
    )
    dlc: int = Field(
        ...,
        description="Number of DLC (type=dlc)",
        ge=0,
        examples=[40],
    )
    bundles: int = Field(
        ...,
        description="Number of bundles (type=bundle)",
        ge=0,
        examples=[10],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "total": 500,
                    "games": 450,
                    "dlc": 40,
                    "bundles": 10,
                }
            ]
        }
    }
