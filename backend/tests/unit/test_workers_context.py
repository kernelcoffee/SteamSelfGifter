"""Unit tests for workers.context.automation_context client cleanup."""

from collections.abc import Iterator
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from services.settings_service import SettingsService
from utils.steam_client import SteamClient
from utils.steamgifts_client import SteamGiftsClient
from workers.context import automation_context


@pytest.fixture
async def session_maker(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory on the test database, with a PHPSESSID configured."""
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        await SettingsService(session).update_settings(phpsessid="test_session")
        await session.commit()
    return maker


@pytest.fixture
def sg_http_clients(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[httpx.AsyncClient]]:
    """Start SteamGifts clients without the network; collects their httpx clients."""
    clients: list[httpx.AsyncClient] = []

    async def sg_start_without_network(self: SteamGiftsClient) -> None:
        self._client = httpx.AsyncClient()
        clients.append(self._client)

    monkeypatch.setattr(SteamGiftsClient, "start", sg_start_without_network)
    yield clients
    for client in clients:
        assert client.is_closed, "a test left a SteamGifts httpx client open"


@pytest.mark.asyncio
async def test_automation_context_closes_both_clients_on_exit(
    session_maker: async_sessionmaker[AsyncSession],
    sg_http_clients: list[httpx.AsyncClient],
) -> None:
    """Both httpx clients are open inside the context and closed when it exits."""
    with patch("workers.context.AsyncSessionLocal", session_maker):
        async with automation_context() as ctx:
            assert ctx.authenticated
            assert ctx.game_service is not None
            steam_http = ctx.game_service.steam_client._client
            assert steam_http is not None
            assert steam_http.is_closed is False
            [sg_http] = sg_http_clients
            assert sg_http.is_closed is False

    assert steam_http.is_closed is True
    assert sg_http.is_closed is True


@pytest.mark.asyncio
async def test_automation_context_closes_sg_client_when_steam_start_fails(
    session_maker: async_sessionmaker[AsyncSession],
    sg_http_clients: list[httpx.AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SteamClient.start raising after the SteamGifts client started does not
    leak the SteamGifts httpx client; the error propagates."""

    async def failing_steam_start(self: SteamClient) -> None:
        raise RuntimeError("steam start failed")

    monkeypatch.setattr(SteamClient, "start", failing_steam_start)

    with patch("workers.context.AsyncSessionLocal", session_maker), pytest.raises(RuntimeError, match="steam start"):
        async with automation_context():
            pytest.fail("the context must not yield when a client fails to start")

    [sg_http] = sg_http_clients
    assert sg_http.is_closed is True


@pytest.mark.asyncio
async def test_automation_context_closes_sg_client_when_its_start_fails(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SteamGiftsClient.start failing after it opened its httpx client (the
    homepage fetch for the XSRF token) still closes that client, and the Steam
    client is never started."""
    sg_http_clients: list[httpx.AsyncClient] = []
    steam_starts: list[SteamClient] = []

    async def sg_start_then_fail(self: SteamGiftsClient) -> None:
        self._client = httpx.AsyncClient()
        sg_http_clients.append(self._client)
        raise RuntimeError("homepage fetch failed")

    async def recording_steam_start(self: SteamClient) -> None:
        steam_starts.append(self)

    monkeypatch.setattr(SteamGiftsClient, "start", sg_start_then_fail)
    monkeypatch.setattr(SteamClient, "start", recording_steam_start)

    with patch("workers.context.AsyncSessionLocal", session_maker), pytest.raises(RuntimeError, match="homepage"):
        async with automation_context():
            pytest.fail("the context must not yield when a client fails to start")

    [sg_http] = sg_http_clients
    assert sg_http.is_closed is True
    assert steam_starts == []


@pytest.mark.asyncio
async def test_automation_context_closes_sg_client_when_steam_close_fails(
    session_maker: async_sessionmaker[AsyncSession],
    sg_http_clients: list[httpx.AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure closing the Steam client still closes the SteamGifts client
    and propagates."""

    async def failing_steam_close(self: SteamClient) -> None:
        raise RuntimeError("steam close failed")

    monkeypatch.setattr(SteamClient, "close", failing_steam_close)

    with patch("workers.context.AsyncSessionLocal", session_maker), pytest.raises(RuntimeError, match="steam close"):
        async with automation_context() as ctx:
            assert ctx.game_service is not None
            steam_http = ctx.game_service.steam_client._client

    [sg_http] = sg_http_clients
    assert sg_http.is_closed is True
    assert steam_http is not None
    await steam_http.aclose()
