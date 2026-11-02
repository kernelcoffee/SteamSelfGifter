"""Request-scoped Steam clients must close after the response finishes."""

from types import SimpleNamespace

import pytest

from api import dependencies as deps


class FakeClient:
    instances = []

    def __init__(self, *args, **kwargs):
        self.started = False
        self.closed = False
        type(self).instances.append(self)

    async def start(self):
        self.started = True

    async def close(self):
        self.closed = True


class FakeSteamGiftsClient(FakeClient):
    instances = []


class FakeSteamClient(FakeClient):
    instances = []


class FakeSettings:
    def __init__(self, db):
        self.db = db

    async def get_settings(self):
        return SimpleNamespace(phpsessid="", user_agent="test")


@pytest.mark.asyncio
async def test_game_service_closes_http_client(monkeypatch):
    monkeypatch.setattr(deps, "SteamClient", FakeSteamClient)
    monkeypatch.setattr(deps, "GameService", lambda db, steam: (db, steam))
    gen = deps.get_game_service(object())
    _, client = await anext(gen)
    assert client.started
    assert not client.closed
    await gen.aclose()
    assert client.closed


@pytest.mark.asyncio
async def test_giveaway_service_closes_both_clients(monkeypatch):
    monkeypatch.setattr(deps, "SteamClient", FakeSteamClient)
    monkeypatch.setattr(deps, "SteamGiftsClient", FakeSteamGiftsClient)
    monkeypatch.setattr(deps, "SettingsService", FakeSettings)
    monkeypatch.setattr(deps, "GameService", lambda db, steam: (db, steam))
    monkeypatch.setattr(deps, "GiveawayService", lambda db, sg, games: (db, sg, games))
    gen = deps.get_giveaway_service(object())
    _, sg, (_, steam) = await anext(gen)
    assert sg.started and steam.started
    await gen.aclose()
    assert sg.closed and steam.closed


@pytest.mark.asyncio
async def test_partial_startup_still_closes_allocated_clients(monkeypatch):
    class FailingSteamClient(FakeSteamClient):
        instances = []

        async def start(self):
            raise RuntimeError("startup failed")

    monkeypatch.setattr(deps, "SteamClient", FailingSteamClient)
    monkeypatch.setattr(deps, "SteamGiftsClient", FakeSteamGiftsClient)
    monkeypatch.setattr(deps, "SettingsService", FakeSettings)

    gen = deps.get_giveaway_service(object())
    with pytest.raises(RuntimeError, match="startup failed"):
        await anext(gen)

    assert FakeSteamGiftsClient.instances[-1].closed
    assert FailingSteamClient.instances[-1].closed
