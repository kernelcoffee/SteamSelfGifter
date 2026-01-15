"""API schemas for entry endpoints.

This module provides Pydantic schemas for giveaway entry-related
API requests and responses.
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class EntryBase(BaseModel):
    """
    Base entry schema with common fields.

    This serves as the base for other entry schemas.
    """

    giveaway_id: int = Field(
        ...,
        description="ID of the giveaway entered",
        examples=[123],
    )
    points_spent: int = Field(
        ...,
        description="Points spent on entry",
        ge=0,
        examples=[50],
    )
    entry_type: str = Field(
        ...,
        description="Type of entry (manual, auto, wishlist)",
        pattern="^(manual|auto|wishlist)$",
        examples=["manual"],
    )
    status: str = Field(
        ...,
        description="Entry status (success, failed)",
        pattern="^(success|failed)$",
        examples=["success"],
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if entry failed",
        examples=["Insufficient points"],
    )


class EntryResponse(EntryBase):
    """
    Entry response schema.

    Extends EntryBase with metadata fields.

    Example:
        >>> entry = EntryResponse(
        ...     id=456,
        ...     giveaway_id=123,
        ...     points_spent=50,
        ...     entry_type="manual",
        ...     status="success",
        ...     entered_at=datetime.utcnow()
        ... )
    """

    id: int = Field(
        ...,
        description="Entry record ID",
        examples=[456],
    )
    entered_at: datetime = Field(
        ...,
        description="When entry was made (UTC)",
        examples=["2025-10-14T11:00:00"],
    )

    model_config = {
        "from_attributes": True,  # Enable ORM mode
        "json_schema_extra": {
            "examples": [
                {
                    "id": 456,
                    "giveaway_id": 123,
                    "points_spent": 50,
                    "entry_type": "manual",
                    "status": "success",
                    "error_message": None,
                    "entered_at": "2025-10-14T11:00:00",
                }
            ]
        },
    }


class EntryList(BaseModel):
    """
    Schema for list of entries.

    Example:
        >>> entries = EntryList(entries=[...])
    """

    entries: list[EntryResponse] = Field(
        ...,
        description="List of entries",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "entries": [
                        {
                            "id": 456,
                            "giveaway_id": 123,
                            "points_spent": 50,
                            "entry_type": "manual",
                            "status": "success",
                            "entered_at": "2025-10-14T11:00:00",
                        }
                    ]
                }
            ]
        }
    }


class EntryFilter(BaseModel):
    """
    Query parameters for filtering entries.

    Example:
        >>> filters = EntryFilter(
        ...     entry_type="auto",
        ...     status="success"
        ... )
    """

    entry_type: Optional[str] = Field(
        default=None,
        description="Filter by entry type (manual, auto, wishlist)",
        pattern="^(manual|auto|wishlist)$",
        examples=["auto"],
    )
    status: Optional[str] = Field(
        default=None,
        description="Filter by status (success, failed)",
        pattern="^(success|failed)$",
        examples=["success"],
    )
    giveaway_id: Optional[int] = Field(
        default=None,
        description="Filter by giveaway ID",
        examples=[123],
    )


class EntryStats(BaseModel):
    """
    Statistics about entries.

    Example:
        >>> stats = EntryStats(
        ...     total=100,
        ...     successful=85,
        ...     failed=15,
        ...     total_points_spent=4250,
        ...     manual_entries=25,
        ...     auto_entries=60,
        ...     wishlist_entries=15
        ... )
    """

    total: int = Field(
        ...,
        description="Total number of entries",
        ge=0,
        examples=[100],
    )
    successful: int = Field(
        ...,
        description="Number of successful entries",
        ge=0,
        examples=[85],
    )
    failed: int = Field(
        ...,
        description="Number of failed entries",
        ge=0,
        examples=[15],
    )
    total_points_spent: int = Field(
        ...,
        description="Total points spent on entries",
        ge=0,
        examples=[4250],
    )
    manual_entries: int = Field(
        ...,
        description="Number of manual entries",
        ge=0,
        examples=[25],
    )
    auto_entries: int = Field(
        ...,
        description="Number of auto entries",
        ge=0,
        examples=[60],
    )
    wishlist_entries: int = Field(
        ...,
        description="Number of wishlist entries",
        ge=0,
        examples=[15],
    )
    success_rate: float = Field(
        ...,
        description="Success rate as percentage",
        ge=0,
        le=100,
        examples=[85.0],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "total": 100,
                    "successful": 85,
                    "failed": 15,
                    "total_points_spent": 4250,
                    "manual_entries": 25,
                    "auto_entries": 60,
                    "wishlist_entries": 15,
                    "success_rate": 85.0,
                }
            ]
        }
    }


class EntryHistoryItem(BaseModel):
    """
    Entry with associated giveaway information.

    Used for entry history displays.

    Example:
        >>> item = EntryHistoryItem(
        ...     entry=EntryResponse(...),
        ...     game_name="Portal 2",
        ...     game_id=620
        ... )
    """

    entry: EntryResponse = Field(
        ...,
        description="Entry details",
    )
    game_name: str = Field(
        ...,
        description="Name of the game",
        examples=["Portal 2"],
    )
    game_id: Optional[int] = Field(
        default=None,
        description="Steam App ID if available",
        examples=[620],
    )
    giveaway_code: str = Field(
        ...,
        description="Giveaway code",
        examples=["AbCd1"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "entry": {
                        "id": 456,
                        "giveaway_id": 123,
                        "points_spent": 50,
                        "entry_type": "manual",
                        "status": "success",
                        "entered_at": "2025-10-14T11:00:00",
                    },
                    "game_name": "Portal 2",
                    "game_id": 620,
                    "giveaway_code": "AbCd1",
                }
            ]
        }
    }


class EntryHistory(BaseModel):
    """
    Schema for entry history list.

    Example:
        >>> history = EntryHistory(entries=[...])
    """

    entries: list[EntryHistoryItem] = Field(
        ...,
        description="List of entry history items",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "entries": [
                        {
                            "entry": {
                                "id": 456,
                                "giveaway_id": 123,
                                "points_spent": 50,
                                "entry_type": "manual",
                                "status": "success",
                                "entered_at": "2025-10-14T11:00:00",
                            },
                            "game_name": "Portal 2",
                            "game_id": 620,
                            "giveaway_code": "AbCd1",
                        }
                    ]
                }
            ]
        }
    }
