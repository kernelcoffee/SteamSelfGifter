"""Unit tests for common API schemas."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from api.schemas.common import (
    ResponseMeta,
    SuccessResponse,
    ErrorDetail,
    ErrorResponse,
    PaginationParams,
    MessageResponse,
    create_success_response,
    create_error_response,
)


def test_response_meta_basic():
    """Test creating basic ResponseMeta."""
    meta = ResponseMeta(timestamp="2025-10-14T12:00:00Z")

    assert meta.timestamp == "2025-10-14T12:00:00Z"
    assert meta.request_id is None
    assert meta.page is None
    assert meta.per_page is None
    assert meta.total is None
    assert meta.total_pages is None


def test_response_meta_with_pagination():
    """Test ResponseMeta with pagination fields."""
    meta = ResponseMeta(
        timestamp="2025-10-14T12:00:00Z",
        page=1,
        per_page=20,
        total=100,
        total_pages=5
    )

    assert meta.page == 1
    assert meta.per_page == 20
    assert meta.total == 100
    assert meta.total_pages == 5


def test_response_meta_with_request_id():
    """Test ResponseMeta with request ID."""
    meta = ResponseMeta(
        timestamp="2025-10-14T12:00:00Z",
        request_id="req_abc123"
    )

    assert meta.request_id == "req_abc123"


def test_response_meta_validation():
    """Test ResponseMeta field validation."""
    # Page must be >= 1
    with pytest.raises(ValidationError):
        ResponseMeta(timestamp="2025-10-14T12:00:00Z", page=0)

    # per_page must be >= 1
    with pytest.raises(ValidationError):
        ResponseMeta(timestamp="2025-10-14T12:00:00Z", per_page=0)

    # per_page must be <= 100
    with pytest.raises(ValidationError):
        ResponseMeta(timestamp="2025-10-14T12:00:00Z", per_page=101)


def test_success_response():
    """Test creating SuccessResponse."""
    meta = ResponseMeta(timestamp="2025-10-14T12:00:00Z")
    response = SuccessResponse[dict](
        success=True,
        data={"id": 123, "name": "Test"},
        meta=meta
    )

    assert response.success is True
    assert response.data == {"id": 123, "name": "Test"}
    assert response.meta == meta


def test_error_detail():
    """Test creating ErrorDetail."""
    error = ErrorDetail(
        code="NOT_FOUND",
        message="Resource not found"
    )

    assert error.code == "NOT_FOUND"
    assert error.message == "Resource not found"
    assert error.details is None


def test_error_detail_with_details():
    """Test ErrorDetail with additional details."""
    error = ErrorDetail(
        code="INSUFFICIENT_POINTS",
        message="Not enough points",
        details={"required": 50, "available": 30}
    )

    assert error.details == {"required": 50, "available": 30}


def test_error_response():
    """Test creating ErrorResponse."""
    error = ErrorDetail(code="NOT_FOUND", message="Not found")
    meta = ResponseMeta(timestamp="2025-10-14T12:00:00Z")

    response = ErrorResponse(
        success=False,
        error=error,
        meta=meta
    )

    assert response.success is False
    assert response.error == error
    assert response.meta == meta


def test_pagination_params_defaults():
    """Test PaginationParams default values."""
    params = PaginationParams()

    assert params.page == 1
    assert params.per_page == 20


def test_pagination_params_custom():
    """Test PaginationParams with custom values."""
    params = PaginationParams(page=3, per_page=50)

    assert params.page == 3
    assert params.per_page == 50


def test_pagination_params_validation():
    """Test PaginationParams validation."""
    # Page must be >= 1
    with pytest.raises(ValidationError):
        PaginationParams(page=0)

    # per_page must be >= 1
    with pytest.raises(ValidationError):
        PaginationParams(per_page=0)

    # per_page must be <= 100
    with pytest.raises(ValidationError):
        PaginationParams(per_page=101)


def test_message_response():
    """Test MessageResponse."""
    response = MessageResponse(message="Operation successful")

    assert response.message == "Operation successful"


def test_create_success_response_basic():
    """Test create_success_response helper."""
    response = create_success_response(data={"id": 123, "name": "Test"})

    assert response["success"] is True
    assert response["data"] == {"id": 123, "name": "Test"}
    assert "meta" in response
    assert "timestamp" in response["meta"]


def test_create_success_response_with_pagination():
    """Test create_success_response with pagination."""
    response = create_success_response(
        data=[1, 2, 3],
        page=1,
        per_page=20,
        total=100
    )

    assert response["meta"]["page"] == 1
    assert response["meta"]["per_page"] == 20
    assert response["meta"]["total"] == 100
    assert response["meta"]["total_pages"] == 5  # 100 / 20


def test_create_success_response_with_request_id():
    """Test create_success_response with request ID."""
    response = create_success_response(
        data={"test": "data"},
        request_id="req_123"
    )

    assert response["meta"]["request_id"] == "req_123"


def test_create_error_response_basic():
    """Test create_error_response helper."""
    response = create_error_response(
        code="NOT_FOUND",
        message="Resource not found"
    )

    assert response["success"] is False
    assert response["error"]["code"] == "NOT_FOUND"
    assert response["error"]["message"] == "Resource not found"
    assert "meta" in response
    assert "timestamp" in response["meta"]


def test_create_error_response_with_details():
    """Test create_error_response with details."""
    response = create_error_response(
        code="VALIDATION_ERROR",
        message="Invalid input",
        details={"field": "email", "error": "Invalid format"}
    )

    assert response["error"]["details"] == {"field": "email", "error": "Invalid format"}


def test_create_error_response_with_request_id():
    """Test create_error_response with request ID."""
    response = create_error_response(
        code="ERROR",
        message="Error occurred",
        request_id="req_456"
    )

    assert response["meta"]["request_id"] == "req_456"


def test_response_meta_serialization():
    """Test ResponseMeta excludes None values in model_dump."""
    meta = ResponseMeta(
        timestamp="2025-10-14T12:00:00Z",
        request_id="req_123"
    )

    dumped = meta.model_dump(exclude_none=True)

    assert "timestamp" in dumped
    assert "request_id" in dumped
    assert "page" not in dumped
    assert "per_page" not in dumped


def test_success_response_with_list_data():
    """Test SuccessResponse with list data."""
    meta = ResponseMeta(timestamp="2025-10-14T12:00:00Z")
    response = SuccessResponse[list](
        success=True,
        data=[{"id": 1}, {"id": 2}, {"id": 3}],
        meta=meta
    )

    assert response.success is True
    assert len(response.data) == 3
    assert response.data[0] == {"id": 1}
