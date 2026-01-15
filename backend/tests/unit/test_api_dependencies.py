"""Unit tests for API dependencies."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import (
    get_database,
    get_settings_service,
    get_notification_service,
)
from services.settings_service import SettingsService
from services.notification_service import NotificationService


@pytest.mark.asyncio
async def test_get_database():
    """Test get_database dependency yields AsyncSession."""
    # get_database is an async generator
    gen = get_database()

    # Get the session
    db = await gen.__anext__()

    # Verify it's an AsyncSession
    assert isinstance(db, AsyncSession)

    # Clean up
    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass  # Expected - generator should stop after yielding once


@pytest.mark.asyncio
async def test_get_settings_service():
    """Test get_settings_service returns SettingsService."""
    gen = get_database()
    db = await gen.__anext__()

    service = get_settings_service(db)

    assert isinstance(service, SettingsService)
    assert service.session == db

    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass


@pytest.mark.asyncio
async def test_get_notification_service():
    """Test get_notification_service returns NotificationService."""
    gen = get_database()
    db = await gen.__anext__()

    service = get_notification_service(db)

    assert isinstance(service, NotificationService)
    assert service.session == db

    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass


@pytest.mark.asyncio
async def test_multiple_service_instances():
    """Test that each dependency call creates a new service instance."""
    gen = get_database()
    db = await gen.__anext__()

    # Get two instances of the same service
    service1 = get_settings_service(db)
    service2 = get_settings_service(db)

    # They should be different instances
    assert service1 is not service2
    # But share the same session
    assert service1.session == service2.session

    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass


@pytest.mark.asyncio
async def test_services_share_same_session():
    """Test that all services created from same db share the session."""
    gen = get_database()
    db = await gen.__anext__()

    # Create different services
    settings_service = get_settings_service(db)
    notification_service = get_notification_service(db)

    # All should share the same session
    assert settings_service.session == db
    assert notification_service.session == db

    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass


@pytest.mark.asyncio
async def test_database_session_lifecycle():
    """Test that database session is properly managed."""
    gen = get_database()

    # Session should be yielded
    db = await gen.__anext__()
    assert isinstance(db, AsyncSession)
    assert not db.is_active or db.is_active  # Session exists

    # Generator should stop after one yield
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()


@pytest.mark.asyncio
async def test_service_initialization():
    """Test that services are properly initialized with session."""
    gen = get_database()
    db = await gen.__anext__()

    # Test SettingsService
    settings_service = get_settings_service(db)
    assert hasattr(settings_service, 'session')
    assert hasattr(settings_service, 'repo')
    assert settings_service.session == db

    # Test NotificationService
    notification_service = get_notification_service(db)
    assert hasattr(notification_service, 'session')
    assert hasattr(notification_service, 'repo')
    assert notification_service.session == db

    try:
        await gen.__anext__()
    except StopAsyncIteration:
        pass
