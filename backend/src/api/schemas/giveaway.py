"""API schemas for giveaway endpoints.

This module provides Pydantic schemas for giveaway-related
API requests and responses.
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_serializer


class GiveawayBase(BaseModel):
    """
    Base giveaway schema with common fields.

    This serves as the base for other giveaway schemas.
    """

    code: str = Field(
        ...,
        description="Unique giveaway code from SteamGifts URL",
        min_length=1,
        examples=["AbCd1"],
    )
    url: str = Field(
        ...,
        description="Full SteamGifts giveaway URL",
        examples=["https://www.steamgifts.com/giveaway/AbCd1/game-name"],
    )
    game_id: Optional[int] = Field(
        default=None,
        description="Steam App ID if available",
        examples=[620],
    )
    game_name: str = Field(
        ...,
        description="Name of the game",
        min_length=1,
        examples=["Portal 2"],
    )
    price: int = Field(
        ...,
        description="Points required to enter",
        ge=0,
        examples=[50],
    )
    copies: int = Field(
        default=1,
        description="Number of copies being given away",
        ge=1,
        examples=[1],
    )
    end_time: Optional[datetime] = Field(
        default=None,
        description="When the giveaway ends (UTC)",
        examples=["2025-10-15T12:00:00"],
    )
    is_hidden: bool = Field(
        default=False,
        description="Whether giveaway is hidden by user",
        examples=[False],
    )
    is_entered: bool = Field(
        default=False,
        description="Whether user has entered this giveaway",
        examples=[False],
    )
    is_wishlist: bool = Field(
        default=False,
        description="Whether game is on user's Steam wishlist",
        examples=[False],
    )
    is_won: bool = Field(
        default=False,
        description="Whether user has won this giveaway",
        examples=[False],
    )
    is_safe: Optional[bool] = Field(
        default=None,
        description="Safety assessment (true=safe, false=unsafe, null=unknown)",
        examples=[True],
    )
    safety_score: Optional[int] = Field(
        default=None,
        description="Safety score (0-100, higher is safer)",
        ge=0,
        le=100,
        examples=[85],
    )


class GiveawayResponse(GiveawayBase):
    """
    Giveaway response schema.

    Extends GiveawayBase with metadata fields.

    Example:
        >>> giveaway = GiveawayResponse(
        ...     id=123,
        ...     code="AbCd1",
        ...     url="https://www.steamgifts.com/giveaway/AbCd1/",
        ...     game_name="Portal 2",
        ...     price=50,
        ...     discovered_at=datetime.utcnow()
        ... )
    """

    id: int = Field(
        ...,
        description="Internal giveaway ID",
        examples=[123],
    )
    discovered_at: datetime = Field(
        ...,
        description="When giveaway was first discovered (UTC)",
        examples=["2025-10-14T10:00:00"],
    )
    entered_at: Optional[datetime] = Field(
        default=None,
        description="When user entered the giveaway (UTC)",
        examples=["2025-10-14T11:00:00"],
    )
    won_at: Optional[datetime] = Field(
        default=None,
        description="When user won the giveaway (UTC)",
        examples=["2025-10-16T12:00:00"],
    )

    # Optional game information from joined Game table
    game_thumbnail: Optional[str] = Field(
        default=None,
        description="Steam header image URL for the game",
        examples=["https://cdn.cloudflare.steamstatic.com/steam/apps/620/header.jpg"],
    )
    game_review_score: Optional[int] = Field(
        default=None,
        description="Steam review score (0-10)",
        ge=0,
        le=10,
        examples=[9],
    )
    game_total_reviews: Optional[int] = Field(
        default=None,
        description="Total number of reviews",
        ge=0,
        examples=[50000],
    )
    game_review_summary: Optional[str] = Field(
        default=None,
        description="Review summary (e.g., 'Overwhelmingly Positive', 'Mixed')",
        examples=["Overwhelmingly Positive"],
    )

    @field_serializer('end_time', 'discovered_at', 'entered_at', 'won_at')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        """Serialize datetime with UTC timezone suffix."""
        if dt is None:
            return None
        # Ensure datetime is formatted as ISO 8601 with Z suffix for UTC
        if dt.tzinfo is None:
            # Assume naive datetimes are UTC
            return dt.isoformat() + 'Z'
        return dt.isoformat()

    model_config = {
        "from_attributes": True,  # Enable ORM mode
        "json_schema_extra": {
            "examples": [
                {
                    "id": 123,
                    "code": "AbCd1",
                    "url": "https://www.steamgifts.com/giveaway/AbCd1/portal-2",
                    "game_id": 620,
                    "game_name": "Portal 2",
                    "price": 50,
                    "copies": 1,
                    "end_time": "2025-10-15T12:00:00Z",
                    "is_hidden": False,
                    "is_entered": True,
                    "is_safe": True,
                    "safety_score": 95,
                    "discovered_at": "2025-10-14T10:00:00Z",
                    "entered_at": "2025-10-14T11:00:00Z",
                }
            ]
        },
    }


class GiveawayList(BaseModel):
    """
    Schema for list of giveaways.

    Example:
        >>> giveaways = GiveawayList(giveaways=[...])
    """

    giveaways: list[GiveawayResponse] = Field(
        ...,
        description="List of giveaways",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "giveaways": [
                        {
                            "id": 123,
                            "code": "AbCd1",
                            "url": "https://www.steamgifts.com/giveaway/AbCd1/",
                            "game_name": "Portal 2",
                            "price": 50,
                            "copies": 1,
                            "is_entered": False,
                            "discovered_at": "2025-10-14T10:00:00",
                        }
                    ]
                }
            ]
        }
    }


class GiveawayFilter(BaseModel):
    """
    Query parameters for filtering giveaways.

    Example:
        >>> filters = GiveawayFilter(
        ...     min_price=50,
        ...     max_price=100,
        ...     is_entered=False
        ... )
    """

    min_price: Optional[int] = Field(
        default=None,
        description="Minimum giveaway price in points",
        ge=0,
        examples=[50],
    )
    max_price: Optional[int] = Field(
        default=None,
        description="Maximum giveaway price in points",
        ge=0,
        examples=[100],
    )
    min_score: Optional[int] = Field(
        default=None,
        description="Minimum Steam review score (0-10)",
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
    is_entered: Optional[bool] = Field(
        default=None,
        description="Filter by entry status",
        examples=[False],
    )
    is_hidden: Optional[bool] = Field(
        default=None,
        description="Filter by hidden status",
        examples=[False],
    )
    search: Optional[str] = Field(
        default=None,
        description="Search by game name",
        examples=["Portal"],
    )


class GiveawayScanRequest(BaseModel):
    """
    Request schema for scanning giveaways.

    Example:
        >>> request = GiveawayScanRequest(pages=5)
    """

    pages: int = Field(
        default=3,
        description="Number of pages to scan",
        ge=1,
        le=10,
        examples=[3],
    )


class GiveawayScanResponse(BaseModel):
    """
    Response schema for scan operations.

    Example:
        >>> response = GiveawayScanResponse(
        ...     new_count=5,
        ...     updated_count=3,
        ...     total_scanned=8
        ... )
    """

    new_count: int = Field(
        ...,
        description="Number of new giveaways found",
        ge=0,
        examples=[5],
    )
    updated_count: int = Field(
        ...,
        description="Number of giveaways updated",
        ge=0,
        examples=[3],
    )
    total_scanned: int = Field(
        ...,
        description="Total giveaways scanned",
        ge=0,
        examples=[8],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "new_count": 5,
                    "updated_count": 3,
                    "total_scanned": 8,
                }
            ]
        }
    }


class GiveawayEntryRequest(BaseModel):
    """
    Request schema for entering a giveaway.

    Example:
        >>> request = GiveawayEntryRequest(entry_type="manual")
    """

    entry_type: str = Field(
        default="manual",
        description="Type of entry (manual, auto, wishlist)",
        pattern="^(manual|auto|wishlist)$",
        examples=["manual"],
    )


class GiveawayEntryResponse(BaseModel):
    """
    Response schema for giveaway entry.

    Example:
        >>> response = GiveawayEntryResponse(
        ...     success=True,
        ...     points_spent=50,
        ...     message="Successfully entered giveaway"
        ... )
    """

    success: bool = Field(
        ...,
        description="Whether entry was successful",
        examples=[True],
    )
    points_spent: int = Field(
        ...,
        description="Points spent on entry",
        ge=0,
        examples=[50],
    )
    message: str = Field(
        ...,
        description="Entry result message",
        examples=["Successfully entered giveaway"],
    )
    entry_id: Optional[int] = Field(
        default=None,
        description="Entry record ID if successful",
        examples=[456],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "points_spent": 50,
                    "message": "Successfully entered giveaway",
                    "entry_id": 456,
                }
            ]
        }
    }


class GiveawayStats(BaseModel):
    """
    Statistics about giveaways.

    Example:
        >>> stats = GiveawayStats(
        ...     total=100,
        ...     active=75,
        ...     entered=25,
        ...     hidden=5
        ... )
    """

    total: int = Field(
        ...,
        description="Total number of giveaways",
        ge=0,
        examples=[100],
    )
    active: int = Field(
        ...,
        description="Number of active (not ended) giveaways",
        ge=0,
        examples=[75],
    )
    entered: int = Field(
        ...,
        description="Number of giveaways entered",
        ge=0,
        examples=[25],
    )
    hidden: int = Field(
        ...,
        description="Number of hidden giveaways",
        ge=0,
        examples=[5],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "total": 100,
                    "active": 75,
                    "entered": 25,
                    "hidden": 5,
                }
            ]
        }
    }
