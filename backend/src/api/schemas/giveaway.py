"""API schemas for giveaway endpoints.

This module provides Pydantic schemas for giveaway-related
API requests and responses.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field, field_serializer

from services.eligibility import DecisionKind, explain, kind_of


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
    game_id: int | None = Field(
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
    entries: int = Field(
        default=0,
        description="Entry count as of the last scan (0 = none yet or unknown)",
        ge=0,
        examples=[250],
    )
    end_time: datetime | None = Field(
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
    is_dlc: bool = Field(
        default=False,
        description="DLC giveaway (DLC listings are for games the user owns)",
        examples=[False],
    )
    is_won: bool = Field(
        default=False,
        description="Whether user has won this giveaway",
        examples=[False],
    )
    is_safe: bool | None = Field(
        default=None,
        description="Safety assessment (true=safe, false=unsafe, null=unknown)",
        examples=[True],
    )
    safety_score: int | None = Field(
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
        ...     discovered_at=utcnow()
        ... )
    """

    id: int = Field(
        ...,
        description="Internal giveaway ID",
        examples=[123],
    )

    @computed_field(  # type: ignore[prop-decorator]  # pydantic-documented mypy limitation
        description="Win chance in percent (copies/entries*100) as of the last scan"
    )
    @property
    def win_chance(self) -> float:
        """Chance to win in percent; 100 when nobody has entered yet.

        Adaptive precision: two decimals for ordinary odds, four for
        long shots so huge giveaways don't all collapse to 0%.
        """
        if self.entries <= 0:
            return 100.0
        raw = self.copies * 100.0 / self.entries
        if raw >= 100.0:
            return 100.0
        if raw >= 1.0:
            return round(raw, 2)
        return max(round(raw, 4), 0.0001)

    discovered_at: datetime = Field(
        ...,
        description="When giveaway was first discovered (UTC)",
        examples=["2025-10-14T10:00:00"],
    )
    entered_at: datetime | None = Field(
        default=None,
        description="When user entered the giveaway (UTC)",
        examples=["2025-10-14T11:00:00"],
    )
    won_at: datetime | None = Field(
        default=None,
        description="When user won the giveaway (UTC)",
        examples=["2025-10-16T12:00:00"],
    )

    # Optional game information from joined Game table
    game_thumbnail: str | None = Field(
        default=None,
        description="Steam header image URL for the game",
        examples=["https://cdn.cloudflare.steamstatic.com/steam/apps/620/header.jpg"],
    )
    game_genres: list[str] | None = Field(
        default=None,
        description="Steam genres of the cached game (null = not cached or not fetched yet)",
        examples=[["Action", "Indie"]],
    )
    game_review_score: int | None = Field(
        default=None,
        description="Steam review score (0-10)",
        ge=0,
        le=10,
        examples=[9],
    )
    game_total_reviews: int | None = Field(
        default=None,
        description="Total number of reviews",
        ge=0,
        examples=[50000],
    )
    game_review_summary: str | None = Field(
        default=None,
        description="Review summary (e.g., 'Overwhelmingly Positive', 'Mixed')",
        examples=["Overwhelmingly Positive"],
    )

    # Autojoin eligibility diagnostics (set during each automation/process cycle)
    eligibility_reason: str | None = Field(
        default=None,
        description="Why this giveaway did/didn't qualify for autojoin at the last "
                    "evaluation (e.g. 'eligible', 'score_below_min', 'no_game_data')",
        examples=["score_below_min"],
    )
    eligibility_checked_at: datetime | None = Field(
        default=None,
        description="When eligibility_reason was last computed (UTC)",
        examples=["2025-10-14T10:05:00"],
    )
    eligibility_detail: dict[str, Any] | None = Field(
        default=None,
        description="Values behind eligibility_reason (actual vs threshold), recorded with it; "
                    "null until a cycle evaluates the giveaway",
        examples=[{"score": 6, "min_score": 7}],
    )

    # computed_field wraps the method in a property itself.
    @computed_field(
        description="eligibility_reason in the user's terms, rendered from the code and the detail; "
                    "null when never evaluated"
    )
    def eligibility_label(self) -> str | None:
        """The last decision explained (services.eligibility.explain)."""
        return explain(self.eligibility_reason, self.eligibility_detail)

    @computed_field(
        description="Family of eligibility_reason: enter, gate, filter or budget; null when "
                    "never evaluated or unknown"
    )
    def eligibility_kind(self) -> DecisionKind | None:
        """The decision family, from registry membership."""
        return kind_of(self.eligibility_reason)

    @field_serializer('end_time', 'discovered_at', 'entered_at', 'won_at', 'eligibility_checked_at')
    def serialize_datetime(self, dt: datetime | None, _info: Any) -> str | None:
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


class DecisionResponse(BaseModel):
    """A live decision from the auto-join engine (preview, eligible, lens)."""

    code: str = Field(..., description="Decision code; always 'eligible' for a candidate", examples=["eligible"])
    label: str = Field(..., description="The decision in the user's terms", examples=["Joinable"])
    detail: dict[str, Any] = Field(
        ...,
        description="The decision's values: priority, rank, lifted_by",
        examples=[{"priority": "wishlist", "rank": 0, "lifted_by": "wishlist"}],
    )
    priority: str | None = Field(
        default=None, description="First matching priority type (null = none)", examples=["wishlist"]
    )
    rank: int = Field(..., description="Index of that item in the priority list (list length = none)", examples=[0])
    lifted_by: str | None = Field(
        default=None,
        description="Exempt priority type that skipped the filters (null = passed them)",
        examples=["wishlist"],
    )


class CandidatePreviewResponse(GiveawayResponse):
    """A giveaway with its live auto-join decision.

    The eligibility_* fields are the last cycle's stored values; ``decision``
    is computed now from the policy and is never stored.
    """

    decision: DecisionResponse = Field(..., description="Live decision from the evaluated policy")


class PolicyPreviewResponse(BaseModel):
    """Dry run of an auto-join policy over the active pool (nothing persisted)."""

    candidates: list[CandidatePreviewResponse] = Field(
        ..., description="Enter candidates in entry order, sliced to limit"
    )
    count: int = Field(..., description="Every enter candidate, before slicing", examples=[12])
    pool: int = Field(..., description="Active, not-entered giveaways evaluated (hidden included)", examples=[40])
    counts: dict[str, int] = Field(
        ..., description="Live decision codes over the pool (sum = pool)",
        examples=[{"eligible": 12, "score_below_min": 20, "hidden": 8}],
    )
    budget_applied: Literal[False] = Field(
        default=False, description="Always false: the points budget and per cycle cap apply at cycle time"
    )


class LensGiveawaysResponse(BaseModel):
    """A tab's giveaways through the auto-join lens: live enter candidates."""

    giveaways: list[CandidatePreviewResponse] = Field(
        ..., description="Enter candidates of the tab's pool in entry order, sliced by limit/offset"
    )
    count: int = Field(..., description="Every enter candidate in the tab's pool (ignores limit/offset)")
    lens: Literal["autojoin"] = Field(..., description="The lens applied")
    budget_applied: Literal[False] = Field(
        default=False, description="Always false: the points budget and per cycle cap apply at cycle time"
    )


class RegistryRule(BaseModel):
    """A gate or an outcome of the auto-join registry."""

    code: str = Field(..., examples=["hidden"])
    label: str = Field(..., examples=["Hidden"])


class RegistryFilter(BaseModel):
    """A filter of the auto-join registry and the setting it reads."""

    code: str = Field(..., examples=["score_below_min"])
    label: str = Field(..., examples=["Review score below minimum"])
    setting: str | None = Field(
        default=None, description="Settings field the filter reads (null = several)", examples=["autojoin_min_score"]
    )


class RegistryParam(BaseModel):
    """A priority item parameter with its bounds."""

    name: str = Field(..., examples=["threshold_minutes"])
    min: int = Field(..., examples=[5])
    max: int = Field(..., examples=[10080])
    default: int = Field(..., examples=[60])


class RegistryPriorityType(BaseModel):
    """A priority type the list may hold."""

    type: str = Field(..., examples=["wishlist"])
    label: str = Field(..., examples=["Wishlist"])
    description: str = Field(..., examples=["Games on your Steam wishlist"])
    exempt_from_filters: bool = Field(..., examples=[True])
    params: list[RegistryParam] = Field(default_factory=list)


class RegistryLimits(BaseModel):
    """Bounds the settings form must respect."""

    genre_max_items: int = Field(..., examples=[50])
    genre_max_length: int = Field(..., examples=[64])
    max_priority_items: int = Field(..., examples=[3])


class AutojoinRegistryResponse(BaseModel):
    """The auto-join registry served as data (GET /giveaways/registry)."""

    gates: list[RegistryRule] = Field(..., description="Gates in precedence order (never lifted)")
    filters: list[RegistryFilter] = Field(..., description="Filters in precedence order")
    outcomes: list[RegistryRule] = Field(..., description="The enter state and the budget outcomes")
    priority_types: list[RegistryPriorityType] = Field(..., description="Priority types in registry order")
    limits: RegistryLimits


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

    min_price: int | None = Field(
        default=None,
        description="Minimum giveaway price in points",
        ge=0,
        examples=[50],
    )
    max_price: int | None = Field(
        default=None,
        description="Maximum giveaway price in points",
        ge=0,
        examples=[100],
    )
    min_score: int | None = Field(
        default=None,
        description="Minimum Steam review score (0-10)",
        ge=0,
        le=10,
        examples=[7],
    )
    min_reviews: int | None = Field(
        default=None,
        description="Minimum number of reviews",
        ge=0,
        examples=[1000],
    )
    is_entered: bool | None = Field(
        default=None,
        description="Filter by entry status",
        examples=[False],
    )
    is_hidden: bool | None = Field(
        default=None,
        description="Filter by hidden status",
        examples=[False],
    )
    search: str | None = Field(
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
    entry_id: int | None = Field(
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
