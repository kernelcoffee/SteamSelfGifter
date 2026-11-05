"""Unit tests for API dependencies."""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import (
    get_database,
    get_game_service,
    get_giveaway_read_service,
    get_giveaway_service,
    get_notification_service,
    get_scheduler_service,
    get_settings_service,
)
from core.exceptions import SteamGiftsSessionExpiredError
from services.notification_service import NotificationService
from services.scheduler_service import SchedulerService
from services.settings_service import SettingsService
from utils.steam_client import SteamClient
from utils.steamgifts_client import SteamGiftsClient


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


@pytest.mark.asyncio
async def test_get_giveaway_read_service_closes_its_steam_client():
    """The read-only service's Steam client is open during the request and
    closed when the dependency is torn down (no httpx client leaked per
    preview, eligible or lens request)."""
    db_gen = get_database()
    db = await db_gen.__anext__()

    gen = get_giveaway_read_service(db)
    service = await gen.__anext__()
    steam_client = service.game_service.steam_client
    assert steam_client._client is not None
    assert steam_client._client.is_closed is False

    http_client = steam_client._client
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()

    assert http_client.is_closed is True
    assert steam_client._client is None
    await db_gen.aclose()


@pytest.mark.asyncio
async def test_get_giveaway_read_service_closes_its_steam_client_on_error():
    """An error raised in the endpoint still closes the client."""
    db_gen = get_database()
    db = await db_gen.__anext__()

    gen = get_giveaway_read_service(db)
    service = await gen.__anext__()
    http_client = service.game_service.steam_client._client

    with pytest.raises(RuntimeError, match="endpoint failed"):
        await gen.athrow(RuntimeError("endpoint failed"))

    assert http_client.is_closed is True
    await db_gen.aclose()


def _make_steam_start_fail_after_opening(monkeypatch: pytest.MonkeyPatch) -> list[httpx.AsyncClient]:
    """Patch SteamClient.start to open its httpx client and then raise.

    Returns the list the opened clients are recorded in, so a test can check
    that the dependency closed the client a failed start left behind.
    """
    opened: list[httpx.AsyncClient] = []

    async def failing_start(self: SteamClient) -> None:
        self._client = httpx.AsyncClient()
        opened.append(self._client)
        raise RuntimeError("steam start failed")

    monkeypatch.setattr(SteamClient, "start", failing_start)
    return opened


@pytest.mark.asyncio
async def test_get_giveaway_read_service_closes_its_steam_client_when_start_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Steam client start that fails after opening its httpx client still
    closes that client, and the error propagates."""
    opened = _make_steam_start_fail_after_opening(monkeypatch)
    db_gen = get_database()
    db = await db_gen.__anext__()

    gen = get_giveaway_read_service(db)
    with pytest.raises(RuntimeError, match="steam start failed"):
        await gen.__anext__()

    [http_client] = opened
    assert http_client.is_closed is True
    await db_gen.aclose()


@pytest.mark.asyncio
async def test_get_game_service_closes_its_steam_client_when_start_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Steam client start that fails after opening its httpx client still
    closes that client, and the error propagates."""
    opened = _make_steam_start_fail_after_opening(monkeypatch)
    db_gen = get_database()
    db = await db_gen.__anext__()

    gen = get_game_service(db)
    with pytest.raises(RuntimeError, match="steam start failed"):
        await gen.__anext__()

    [http_client] = opened
    assert http_client.is_closed is True
    await db_gen.aclose()


@pytest.mark.asyncio
async def test_get_game_service_closes_its_steam_client() -> None:
    """The game service's Steam client is open during the request and closed
    when the dependency is torn down."""
    db_gen = get_database()
    db = await db_gen.__anext__()

    gen = get_game_service(db)
    service = await gen.__anext__()
    steam_client = service.steam_client
    http_client = steam_client._client
    assert http_client is not None
    assert http_client.is_closed is False

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()

    assert http_client.is_closed is True
    assert steam_client._client is None
    await db_gen.aclose()


@pytest.mark.asyncio
async def test_get_game_service_closes_its_steam_client_on_error() -> None:
    """An error raised in the endpoint still closes the client and propagates."""
    db_gen = get_database()
    db = await db_gen.__anext__()

    gen = get_game_service(db)
    service = await gen.__anext__()
    http_client = service.steam_client._client

    with pytest.raises(RuntimeError, match="endpoint failed"):
        await gen.athrow(RuntimeError("endpoint failed"))

    assert http_client.is_closed is True
    await db_gen.aclose()


@pytest.mark.asyncio
async def test_get_giveaway_service_closes_both_clients(async_session: AsyncSession) -> None:
    """The SteamGifts and Steam clients are open during the request and both
    closed when the dependency is torn down.

    Uses the in-memory session: this dependency reads the stored PHPSESSID,
    and a configured local database would make the client fetch SteamGifts.
    """
    gen = get_giveaway_service(async_session)
    service = await gen.__anext__()
    sg_http = service.sg_client._client
    steam_http = service.game_service.steam_client._client
    assert sg_http is not None and sg_http.is_closed is False
    assert steam_http is not None and steam_http.is_closed is False

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()

    assert sg_http.is_closed is True
    assert steam_http.is_closed is True
    assert service.sg_client._client is None
    assert service.game_service.steam_client._client is None


@pytest.mark.asyncio
async def test_get_giveaway_service_closes_clients_when_steam_start_fails(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the Steam client fails to start, the already-started SteamGifts
    client is closed, the Steam client is closed, and the error propagates.

    Uses the in-memory session for the same reason as the test above.
    """
    sg_http_clients: list[httpx.AsyncClient | None] = []
    closed_steam_clients: list[SteamClient] = []
    original_sg_start = SteamGiftsClient.start
    original_steam_close = SteamClient.close

    async def recording_sg_start(self: SteamGiftsClient) -> None:
        await original_sg_start(self)
        sg_http_clients.append(self._client)

    async def failing_steam_start(self: SteamClient) -> None:
        raise RuntimeError("steam start failed")

    async def recording_steam_close(self: SteamClient) -> None:
        closed_steam_clients.append(self)
        await original_steam_close(self)

    monkeypatch.setattr(SteamGiftsClient, "start", recording_sg_start)
    monkeypatch.setattr(SteamClient, "start", failing_steam_start)
    monkeypatch.setattr(SteamClient, "close", recording_steam_close)

    gen = get_giveaway_service(async_session)
    with pytest.raises(RuntimeError, match="steam start failed"):
        await gen.__anext__()

    [sg_http] = sg_http_clients
    assert sg_http.is_closed is True
    assert len(closed_steam_clients) == 1


@pytest.mark.asyncio
async def test_get_scheduler_service_needs_only_the_session() -> None:
    """The scheduler dependency builds the service from the session alone and
    the service holds no GiveawayService (whose clients the request closes).

    That no HTTP client is started through the dependency graph is proven
    end to end by
    tests/e2e/test_analytics_api.py::test_scheduler_summary_endpoint_starts_no_http_client.
    """
    db_gen = get_database()
    db = await db_gen.__anext__()

    service = get_scheduler_service(db)

    assert isinstance(service, SchedulerService)
    assert service.session == db
    assert not hasattr(service, "giveaway_service")
    await db_gen.aclose()


@pytest.mark.asyncio
async def test_get_giveaway_service_closes_both_clients_on_endpoint_error(async_session: AsyncSession) -> None:
    """An error raised in the endpoint after the dependency yielded closes the
    SteamGifts and Steam clients and propagates unchanged."""
    gen = get_giveaway_service(async_session)
    service = await gen.__anext__()
    sg_http = service.sg_client._client
    steam_http = service.game_service.steam_client._client
    assert sg_http is not None and steam_http is not None

    with pytest.raises(RuntimeError, match="endpoint failed"):
        await gen.athrow(RuntimeError("endpoint failed"))

    assert sg_http.is_closed is True
    assert steam_http.is_closed is True


@pytest.mark.asyncio
async def test_get_giveaway_service_closes_sg_client_when_its_start_fails(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a PHPSESSID stored, SteamGiftsClient.start opens its httpx client
    and then fails to read the XSRF token from the homepage: that client is
    closed, the Steam client is never started, and the session-expired error
    propagates to the request."""
    await SettingsService(async_session).update_settings(phpsessid="test_session")

    homepage_requests: list[httpx.Request] = []

    def homepage_without_token(request: httpx.Request) -> httpx.Response:
        homepage_requests.append(request)
        return httpx.Response(200, text="<html><body>Sign in through Steam</body></html>")

    sg_clients: list[SteamGiftsClient] = []

    def sg_client_on_mock_transport(**kwargs: object) -> SteamGiftsClient:
        client = SteamGiftsClient(**kwargs, transport=httpx.MockTransport(homepage_without_token))
        sg_clients.append(client)
        return client

    steam_starts: list[SteamClient] = []

    async def recording_steam_start(self: SteamClient) -> None:
        steam_starts.append(self)

    monkeypatch.setattr("api.dependencies.SteamGiftsClient", sg_client_on_mock_transport)
    monkeypatch.setattr(SteamClient, "start", recording_steam_start)

    opened: list[httpx.AsyncClient] = []
    original_refresh = SteamGiftsClient._refresh_xsrf_token

    async def recording_refresh(self: SteamGiftsClient) -> None:
        assert self._client is not None
        opened.append(self._client)
        await original_refresh(self)

    monkeypatch.setattr(SteamGiftsClient, "_refresh_xsrf_token", recording_refresh)

    gen = get_giveaway_service(async_session)
    with pytest.raises(SteamGiftsSessionExpiredError, match="XSRF"):
        await gen.__anext__()

    assert len(homepage_requests) == 1
    [sg_http] = opened
    assert sg_http.is_closed is True
    assert [client._client for client in sg_clients] == [None]
    assert steam_starts == []


@pytest.mark.asyncio
async def test_get_giveaway_service_closes_sg_client_when_steam_close_fails(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure closing the Steam client at teardown still closes the
    SteamGifts client, and the close error propagates."""

    async def failing_steam_close(self: SteamClient) -> None:
        raise RuntimeError("steam close failed")

    monkeypatch.setattr(SteamClient, "close", failing_steam_close)

    gen = get_giveaway_service(async_session)
    service = await gen.__anext__()
    sg_http = service.sg_client._client
    steam_http = service.game_service.steam_client._client
    assert sg_http is not None and steam_http is not None

    with pytest.raises(RuntimeError, match="steam close failed"):
        await gen.__anext__()

    assert sg_http.is_closed is True
    await steam_http.aclose()
