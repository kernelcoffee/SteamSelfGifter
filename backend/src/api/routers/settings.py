"""Settings API router for managing application configuration.

This module provides REST API endpoints for settings management,
including authentication, automation, and configuration validation.
"""

from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any

from api.dependencies import SettingsServiceDep
from api.schemas.settings import (
    SettingsResponse,
    SettingsUpdate,
    SteamGiftsCredentials,
    ConfigurationValidation,
)
from api.schemas.common import (
    MessageResponse,
    create_success_response,
    create_error_response,
)

router = APIRouter()


@router.get(
    "",
    response_model=Dict[str, Any],
    summary="Get application settings",
    description="Retrieve current application settings including authentication, automation, and configuration.",
)
async def get_settings(settings_service: SettingsServiceDep) -> Dict[str, Any]:
    """
    Get application settings.

    Returns:
        Success response with settings data

    Example response:
        {
            "success": true,
            "data": {
                "id": 1,
                "phpsessid": "abc123...",
                "autojoin_enabled": true,
                ...
            },
            "meta": {
                "timestamp": "2025-10-14T12:00:00Z"
            }
        }
    """
    settings = await settings_service.get_settings()

    # Convert to schema for validation
    settings_data = SettingsResponse.model_validate(settings)

    return create_success_response(data=settings_data.model_dump())


@router.put(
    "",
    response_model=Dict[str, Any],
    summary="Update application settings",
    description="Update application settings. All fields are optional for partial updates.",
)
async def update_settings(
    update_data: SettingsUpdate,
    settings_service: SettingsServiceDep,
) -> Dict[str, Any]:
    """
    Update application settings.

    Args:
        update_data: Settings fields to update (partial update supported)

    Returns:
        Success response with updated settings

    Raises:
        HTTPException: 400 if validation fails

    Example request:
        {
            "autojoin_enabled": true,
            "autojoin_min_price": 50,
            "max_entries_per_cycle": 15
        }
    """
    try:
        # Get only non-None fields from update
        update_dict = update_data.model_dump(exclude_none=True)

        if not update_dict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update"
            )

        # Update settings
        settings = await settings_service.update_settings(**update_dict)

        # Convert to schema
        settings_data = SettingsResponse.model_validate(settings)

        return create_success_response(data=settings_data.model_dump())

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/credentials",
    response_model=Dict[str, Any],
    summary="Set SteamGifts credentials",
    description="Configure SteamGifts authentication credentials (PHPSESSID cookie).",
)
async def set_credentials(
    credentials: SteamGiftsCredentials,
    settings_service: SettingsServiceDep,
) -> Dict[str, Any]:
    """
    Set SteamGifts authentication credentials.

    Args:
        credentials: PHPSESSID and optional user agent

    Returns:
        Success response with updated settings

    Raises:
        HTTPException: 400 if validation fails

    Example request:
        {
            "phpsessid": "abc123def456...",
            "user_agent": "Mozilla/5.0 ..."
        }
    """
    try:
        settings = await settings_service.set_steamgifts_credentials(
            phpsessid=credentials.phpsessid,
            user_agent=credentials.user_agent
        )

        settings_data = SettingsResponse.model_validate(settings)

        return create_success_response(data=settings_data.model_dump())

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete(
    "/credentials",
    response_model=Dict[str, Any],
    summary="Clear SteamGifts credentials",
    description="Remove SteamGifts authentication credentials.",
)
async def clear_credentials(
    settings_service: SettingsServiceDep,
) -> Dict[str, Any]:
    """
    Clear SteamGifts credentials.

    Returns:
        Success response with confirmation message
    """
    await settings_service.clear_steamgifts_credentials()

    return create_success_response(
        data={"message": "Credentials cleared successfully"}
    )


@router.post(
    "/validate",
    response_model=Dict[str, Any],
    summary="Validate configuration",
    description="Validate current settings configuration and return any errors or warnings.",
)
async def validate_configuration(
    settings_service: SettingsServiceDep,
) -> Dict[str, Any]:
    """
    Validate current configuration.

    Returns:
        Validation results with errors and warnings

    Example response:
        {
            "success": true,
            "data": {
                "is_valid": false,
                "errors": ["PHPSESSID not configured"],
                "warnings": []
            },
            "meta": {
                "timestamp": "2025-10-14T12:00:00Z"
            }
        }
    """
    result = await settings_service.validate_configuration()

    validation_data = ConfigurationValidation.model_validate(result)

    return create_success_response(data=validation_data.model_dump())


@router.post(
    "/reset",
    response_model=Dict[str, Any],
    summary="Reset settings to defaults",
    description="Reset all settings to default values while preserving credentials.",
)
async def reset_to_defaults(
    settings_service: SettingsServiceDep,
) -> Dict[str, Any]:
    """
    Reset settings to default values.

    Credentials (PHPSESSID, user agent) are preserved.

    Returns:
        Success response with reset settings
    """
    settings = await settings_service.reset_to_defaults()

    settings_data = SettingsResponse.model_validate(settings)

    return create_success_response(data=settings_data.model_dump())


@router.post(
    "/test-session",
    response_model=Dict[str, Any],
    summary="Test SteamGifts session",
    description="Validate the current PHPSESSID by fetching user info from SteamGifts.",
)
async def test_session(
    settings_service: SettingsServiceDep,
) -> Dict[str, Any]:
    """
    Test SteamGifts session validity.

    Attempts to fetch user info from SteamGifts using the configured PHPSESSID.

    Returns:
        Success response with session validity and user info if valid

    Example response (valid):
        {
            "success": true,
            "data": {
                "valid": true,
                "username": "MyUsername",
                "points": 350
            }
        }

    Example response (invalid):
        {
            "success": true,
            "data": {
                "valid": false,
                "error": "Not authenticated"
            }
        }
    """
    result = await settings_service.test_session()
    return create_success_response(data=result)


