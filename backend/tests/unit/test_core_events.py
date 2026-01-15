"""Unit tests for WebSocket event manager."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from core.events import EventManager, event_manager


@pytest.fixture
def manager():
    """Create a fresh EventManager for each test."""
    return EventManager()


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection."""
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_text = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_event_manager_initialization(manager):
    """Test EventManager initializes with empty connections."""
    assert manager.active_connections == set()
    assert manager.get_connection_count() == 0


@pytest.mark.asyncio
async def test_connect_websocket(manager, mock_websocket):
    """Test connecting a WebSocket client."""
    await manager.connect(mock_websocket)

    mock_websocket.accept.assert_called_once()
    assert mock_websocket in manager.active_connections
    assert manager.get_connection_count() == 1


@pytest.mark.asyncio
async def test_connect_multiple_websockets(manager):
    """Test connecting multiple WebSocket clients."""
    ws1 = MagicMock()
    ws1.accept = AsyncMock()
    ws2 = MagicMock()
    ws2.accept = AsyncMock()
    ws3 = MagicMock()
    ws3.accept = AsyncMock()

    await manager.connect(ws1)
    await manager.connect(ws2)
    await manager.connect(ws3)

    assert manager.get_connection_count() == 3
    assert ws1 in manager.active_connections
    assert ws2 in manager.active_connections
    assert ws3 in manager.active_connections


@pytest.mark.asyncio
async def test_disconnect_websocket(manager, mock_websocket):
    """Test disconnecting a WebSocket client."""
    await manager.connect(mock_websocket)
    assert manager.get_connection_count() == 1

    manager.disconnect(mock_websocket)

    assert mock_websocket not in manager.active_connections
    assert manager.get_connection_count() == 0


@pytest.mark.asyncio
async def test_disconnect_nonexistent_websocket(manager, mock_websocket):
    """Test disconnecting a WebSocket that was never connected."""
    # Should not raise an error
    manager.disconnect(mock_websocket)
    assert manager.get_connection_count() == 0


@pytest.mark.asyncio
async def test_disconnect_already_disconnected(manager, mock_websocket):
    """Test disconnecting a WebSocket twice."""
    await manager.connect(mock_websocket)
    manager.disconnect(mock_websocket)

    # Disconnecting again should not raise an error
    manager.disconnect(mock_websocket)
    assert manager.get_connection_count() == 0


@pytest.mark.asyncio
async def test_send_event(manager, mock_websocket):
    """Test sending event to specific WebSocket."""
    event = {"type": "test", "data": {"message": "hello"}}

    await manager.send_event(mock_websocket, event)

    mock_websocket.send_json.assert_called_once_with(event)


@pytest.mark.asyncio
async def test_broadcast_event_single_client(manager, mock_websocket):
    """Test broadcasting event to single connected client."""
    await manager.connect(mock_websocket)

    with patch('core.events.datetime') as mock_datetime:
        mock_datetime.utcnow.return_value = datetime(2024, 1, 15, 10, 30, 0)

        await manager.broadcast_event("scan_complete", {"new": 5, "updated": 3})

    # Verify event was sent
    mock_websocket.send_json.assert_called_once()
    sent_event = mock_websocket.send_json.call_args[0][0]

    assert sent_event["type"] == "scan_complete"
    assert sent_event["data"] == {"new": 5, "updated": 3}
    assert "timestamp" in sent_event


@pytest.mark.asyncio
async def test_broadcast_event_multiple_clients(manager):
    """Test broadcasting event to multiple connected clients."""
    ws1 = MagicMock()
    ws1.accept = AsyncMock()
    ws1.send_json = AsyncMock()
    ws2 = MagicMock()
    ws2.accept = AsyncMock()
    ws2.send_json = AsyncMock()
    ws3 = MagicMock()
    ws3.accept = AsyncMock()
    ws3.send_json = AsyncMock()

    await manager.connect(ws1)
    await manager.connect(ws2)
    await manager.connect(ws3)

    await manager.broadcast_event("test_event", {"message": "broadcast"})

    # All clients should receive the event
    ws1.send_json.assert_called_once()
    ws2.send_json.assert_called_once()
    ws3.send_json.assert_called_once()


@pytest.mark.asyncio
async def test_broadcast_event_no_clients(manager):
    """Test broadcasting event with no connected clients."""
    # Should not raise an error
    await manager.broadcast_event("test_event", {"message": "nobody home"})

    assert manager.get_connection_count() == 0


@pytest.mark.asyncio
async def test_broadcast_event_removes_disconnected_clients(manager):
    """Test that broadcast removes clients that fail to receive."""
    ws1 = MagicMock()
    ws1.accept = AsyncMock()
    ws1.send_json = AsyncMock()
    ws2 = MagicMock()
    ws2.accept = AsyncMock()
    ws2.send_json = AsyncMock(side_effect=Exception("Connection closed"))
    ws3 = MagicMock()
    ws3.accept = AsyncMock()
    ws3.send_json = AsyncMock()

    await manager.connect(ws1)
    await manager.connect(ws2)
    await manager.connect(ws3)

    assert manager.get_connection_count() == 3

    await manager.broadcast_event("test_event", {"data": "test"})

    # ws2 should be removed due to send failure
    assert manager.get_connection_count() == 2
    assert ws1 in manager.active_connections
    assert ws2 not in manager.active_connections
    assert ws3 in manager.active_connections


@pytest.mark.asyncio
async def test_broadcast_notification(manager, mock_websocket):
    """Test broadcasting notification message."""
    await manager.connect(mock_websocket)

    await manager.broadcast_notification(
        "info",
        "Entered giveaway for Portal 2",
        {"points": 50}
    )

    mock_websocket.send_json.assert_called_once()
    sent_event = mock_websocket.send_json.call_args[0][0]

    assert sent_event["type"] == "notification"
    assert sent_event["data"]["level"] == "info"
    assert sent_event["data"]["message"] == "Entered giveaway for Portal 2"
    assert sent_event["data"]["details"] == {"points": 50}


@pytest.mark.asyncio
async def test_broadcast_notification_without_details(manager, mock_websocket):
    """Test broadcasting notification without details."""
    await manager.connect(mock_websocket)

    await manager.broadcast_notification("warning", "Low points remaining")

    sent_event = mock_websocket.send_json.call_args[0][0]
    assert sent_event["data"]["details"] == {}


@pytest.mark.asyncio
async def test_broadcast_stats_update(manager, mock_websocket):
    """Test broadcasting statistics update."""
    await manager.connect(mock_websocket)

    stats = {
        "current_points": 450,
        "total_entries": 23,
        "active_giveaways": 142
    }

    await manager.broadcast_stats_update(stats)

    sent_event = mock_websocket.send_json.call_args[0][0]
    assert sent_event["type"] == "stats_update"
    assert sent_event["data"] == stats


@pytest.mark.asyncio
async def test_broadcast_scan_progress(manager, mock_websocket):
    """Test broadcasting scan progress."""
    await manager.connect(mock_websocket)

    await manager.broadcast_scan_progress(
        current_page=2,
        total_pages=3,
        found=15
    )

    sent_event = mock_websocket.send_json.call_args[0][0]
    assert sent_event["type"] == "scan_progress"
    assert sent_event["data"]["current_page"] == 2
    assert sent_event["data"]["total_pages"] == 3
    assert sent_event["data"]["found"] == 15


@pytest.mark.asyncio
async def test_get_connection_count(manager):
    """Test getting active connection count."""
    assert manager.get_connection_count() == 0

    ws1 = MagicMock()
    ws1.accept = AsyncMock()
    ws2 = MagicMock()
    ws2.accept = AsyncMock()

    await manager.connect(ws1)
    assert manager.get_connection_count() == 1

    await manager.connect(ws2)
    assert manager.get_connection_count() == 2

    manager.disconnect(ws1)
    assert manager.get_connection_count() == 1

    manager.disconnect(ws2)
    assert manager.get_connection_count() == 0


@pytest.mark.asyncio
async def test_event_structure(manager, mock_websocket):
    """Test that broadcast events have correct structure."""
    await manager.connect(mock_websocket)

    with patch('core.events.datetime') as mock_datetime:
        mock_datetime.utcnow.return_value = datetime(2024, 1, 15, 10, 30, 45)

        await manager.broadcast_event("test_type", {"key": "value"})

    sent_event = mock_websocket.send_json.call_args[0][0]

    # Verify event structure
    assert "type" in sent_event
    assert "data" in sent_event
    assert "timestamp" in sent_event
    assert sent_event["type"] == "test_type"
    assert sent_event["data"] == {"key": "value"}
    assert sent_event["timestamp"] == "2024-01-15T10:30:45"


@pytest.mark.asyncio
async def test_global_event_manager():
    """Test that global event_manager is an EventManager instance."""
    assert isinstance(event_manager, EventManager)
    # Global manager should be usable
    assert hasattr(event_manager, 'active_connections')
    assert hasattr(event_manager, 'broadcast_event')


@pytest.mark.asyncio
async def test_concurrent_broadcasts(manager):
    """Test multiple concurrent broadcasts."""
    ws1 = MagicMock()
    ws1.accept = AsyncMock()
    ws1.send_json = AsyncMock()

    await manager.connect(ws1)

    # Send multiple events concurrently
    await manager.broadcast_event("event1", {"id": 1})
    await manager.broadcast_event("event2", {"id": 2})
    await manager.broadcast_event("event3", {"id": 3})

    # All events should be sent
    assert ws1.send_json.call_count == 3
