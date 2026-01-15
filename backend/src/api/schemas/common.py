"""Common API schemas for standardized responses.

This module provides base Pydantic schemas for API responses,
ensuring consistent response structure across all endpoints.
"""

from typing import Any, Optional, Generic, TypeVar
from datetime import datetime
from pydantic import BaseModel, Field


# Generic type variable for data payload
T = TypeVar("T")


class ResponseMeta(BaseModel):
    """
    Metadata for API responses.

    Attributes:
        timestamp: Response timestamp in ISO format
        request_id: Optional request identifier for tracing
        page: Current page number (for paginated responses)
        per_page: Items per page (for paginated responses)
        total: Total number of items (for paginated responses)
        total_pages: Total number of pages (for paginated responses)

    Example:
        >>> meta = ResponseMeta(timestamp="2025-10-14T12:00:00Z")
        >>> meta.timestamp
        '2025-10-14T12:00:00Z'
    """

    timestamp: str = Field(
        ...,
        description="Response timestamp in ISO 8601 format",
        examples=["2025-10-14T12:00:00Z"],
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Request identifier for tracing",
        examples=["req_abc123"],
    )

    # Pagination fields (optional)
    page: Optional[int] = Field(
        default=None,
        description="Current page number (1-indexed)",
        ge=1,
        examples=[1],
    )
    per_page: Optional[int] = Field(
        default=None,
        description="Items per page",
        ge=1,
        le=100,
        examples=[20],
    )
    total: Optional[int] = Field(
        default=None,
        description="Total number of items",
        ge=0,
        examples=[100],
    )
    total_pages: Optional[int] = Field(
        default=None,
        description="Total number of pages",
        ge=0,
        examples=[5],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"timestamp": "2025-10-14T12:00:00Z"},
                {
                    "timestamp": "2025-10-14T12:00:00Z",
                    "page": 1,
                    "per_page": 20,
                    "total": 100,
                    "total_pages": 5,
                },
            ]
        }
    }


class SuccessResponse(BaseModel, Generic[T]):
    """
    Standard success response wrapper.

    This is a generic response that wraps successful API responses
    with consistent structure.

    Type Parameters:
        T: Type of the data payload

    Attributes:
        success: Always True for success responses
        data: Response data (generic type)
        meta: Response metadata

    Example:
        >>> from pydantic import BaseModel
        >>> class GameData(BaseModel):
        ...     id: int
        ...     name: str
        >>> response = SuccessResponse[GameData](
        ...     success=True,
        ...     data=GameData(id=123, name="Portal 2"),
        ...     meta=ResponseMeta(timestamp="2025-10-14T12:00:00Z")
        ... )
    """

    success: bool = Field(
        default=True,
        description="Success status (always true)",
        examples=[True],
    )
    data: T = Field(
        ...,
        description="Response data payload",
    )
    meta: ResponseMeta = Field(
        ...,
        description="Response metadata",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "data": {"id": "123", "name": "Game Name"},
                    "meta": {"timestamp": "2025-10-14T12:00:00Z"},
                }
            ]
        }
    }


class ErrorDetail(BaseModel):
    """
    Error details structure.

    Attributes:
        code: Machine-readable error code
        message: Human-readable error message
        details: Optional additional error details

    Example:
        >>> error = ErrorDetail(
        ...     code="INSUFFICIENT_POINTS",
        ...     message="Not enough points to enter this giveaway",
        ...     details={"required": 50, "available": 30}
        ... )
    """

    code: str = Field(
        ...,
        description="Machine-readable error code",
        examples=["INSUFFICIENT_POINTS", "NOT_FOUND", "VALIDATION_ERROR"],
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
        examples=["Not enough points to enter this giveaway"],
    )
    details: Optional[dict[str, Any]] = Field(
        default=None,
        description="Additional error details",
        examples=[{"required": 50, "available": 30}],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "code": "INSUFFICIENT_POINTS",
                    "message": "Not enough points to enter this giveaway",
                    "details": {"required": 50, "available": 30},
                }
            ]
        }
    }


class ErrorResponse(BaseModel):
    """
    Standard error response wrapper.

    Attributes:
        success: Always False for error responses
        error: Error details
        meta: Response metadata

    Example:
        >>> response = ErrorResponse(
        ...     success=False,
        ...     error=ErrorDetail(
        ...         code="NOT_FOUND",
        ...         message="Giveaway not found"
        ...     ),
        ...     meta=ResponseMeta(timestamp="2025-10-14T12:00:00Z")
        ... )
    """

    success: bool = Field(
        default=False,
        description="Success status (always false)",
        examples=[False],
    )
    error: ErrorDetail = Field(
        ...,
        description="Error details",
    )
    meta: ResponseMeta = Field(
        ...,
        description="Response metadata",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": False,
                    "error": {
                        "code": "INSUFFICIENT_POINTS",
                        "message": "Not enough points to enter this giveaway",
                        "details": {"required": 50, "available": 30},
                    },
                    "meta": {
                        "timestamp": "2025-10-14T12:00:00Z",
                        "request_id": "req_abc123",
                    },
                }
            ]
        }
    }


class PaginationParams(BaseModel):
    """
    Query parameters for pagination.

    Attributes:
        page: Page number (1-indexed)
        per_page: Items per page (default: 20, max: 100)

    Example:
        >>> params = PaginationParams(page=1, per_page=20)
    """

    page: int = Field(
        default=1,
        description="Page number (1-indexed)",
        ge=1,
        examples=[1],
    )
    per_page: int = Field(
        default=20,
        description="Items per page",
        ge=1,
        le=100,
        examples=[20],
    )


class MessageResponse(BaseModel):
    """
    Simple message response for operations that don't return data.

    Attributes:
        message: Response message

    Example:
        >>> response = MessageResponse(message="Settings updated successfully")
    """

    message: str = Field(
        ...,
        description="Response message",
        examples=["Settings updated successfully", "Giveaway entered successfully"],
    )


def create_success_response(
    data: Any,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
    total: Optional[int] = None,
    request_id: Optional[str] = None,
) -> dict:
    """
    Helper function to create a success response dictionary.

    Args:
        data: Response data payload
        page: Current page number (for paginated responses)
        per_page: Items per page (for paginated responses)
        total: Total number of items (for paginated responses)
        request_id: Optional request identifier

    Returns:
        Dictionary with success response structure

    Example:
        >>> response = create_success_response(
        ...     data={"id": 123, "name": "Portal 2"},
        ...     request_id="req_abc123"
        ... )
        >>> response["success"]
        True
    """
    meta = ResponseMeta(
        timestamp=datetime.utcnow().isoformat() + "Z",
        request_id=request_id,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=(total + per_page - 1) // per_page if total and per_page else None,
    )

    return {
        "success": True,
        "data": data,
        "meta": meta.model_dump(exclude_none=True),
    }


def create_error_response(
    code: str,
    message: str,
    details: Optional[dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> dict:
    """
    Helper function to create an error response dictionary.

    Args:
        code: Machine-readable error code
        message: Human-readable error message
        details: Optional additional error details
        request_id: Optional request identifier

    Returns:
        Dictionary with error response structure

    Example:
        >>> response = create_error_response(
        ...     code="NOT_FOUND",
        ...     message="Giveaway not found",
        ...     details={"code": "AbCd1"}
        ... )
        >>> response["success"]
        False
    """
    meta = ResponseMeta(
        timestamp=datetime.utcnow().isoformat() + "Z",
        request_id=request_id,
    )

    error = ErrorDetail(
        code=code,
        message=message,
        details=details,
    )

    return {
        "success": False,
        "error": error.model_dump(exclude_none=True),
        "meta": meta.model_dump(exclude_none=True),
    }
