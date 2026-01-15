"""Unit tests for WebSocket router."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import WebSocketDisconnect

from api.routers.websocket import websocket_endpoint
from core.events import EventManager


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection."""
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.send_text = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


@pytest.fixture
def mock_event_manager():
    """Create a mock EventManager."""
    manager = MagicMock(spec=EventManager)
    manager.connect = AsyncMock()
    manager.disconnect = MagicMock()
    return manager


@pytest.mark.asyncio
async def test_websocket_endpoint_accepts_connection(mock_websocket, mock_event_manager):
    """Test that WebSocket endpoint accepts and registers connection."""
    # Make receive_text raise WebSocketDisconnect to exit the loop
    mock_websocket.receive_text.side_effect = WebSocketDisconnect()

    with patch('api.routers.websocket.event_manager', mock_event_manager):
        await websocket_endpoint(mock_websocket)

    # Verify connection was accepted and registered
    mock_event_manager.connect.assert_called_once_with(mock_websocket)


@pytest.mark.asyncio
async def test_websocket_endpoint_handles_disconnect(mock_websocket, mock_event_manager):
    """Test that WebSocket endpoint handles client disconnect."""
    # Simulate client disconnect
    mock_websocket.receive_text.side_effect = WebSocketDisconnect()

    with patch('api.routers.websocket.event_manager', mock_event_manager):
        await websocket_endpoint(mock_websocket)

    # Verify connection was cleaned up
    mock_event_manager.disconnect.assert_called_once_with(mock_websocket)


@pytest.mark.asyncio
async def test_websocket_endpoint_receives_messages(mock_websocket, mock_event_manager):
    """Test that WebSocket endpoint receives client messages."""
    # Simulate receiving a few messages before disconnect
    messages = ["ping", "keepalive", "ping"]
    mock_websocket.receive_text.side_effect = messages + [WebSocketDisconnect()]

    with patch('api.routers.websocket.event_manager', mock_event_manager):
        await websocket_endpoint(mock_websocket)

    # Verify we attempted to receive messages
    assert mock_websocket.receive_text.call_count == len(messages) + 1


@pytest.mark.asyncio
async def test_websocket_endpoint_keeps_connection_alive(mock_websocket, mock_event_manager):
    """Test that WebSocket endpoint maintains connection."""
    call_count = 0

    async def receive_side_effect():
        nonlocal call_count
        call_count += 1
        if call_count > 5:
            raise WebSocketDisconnect()
        return "ping"

    mock_websocket.receive_text.side_effect = receive_side_effect

    with patch('api.routers.websocket.event_manager', mock_event_manager):
        await websocket_endpoint(mock_websocket)

    # Connection should have been maintained for multiple messages
    assert call_count == 6  # 5 successful receives + 1 disconnect


@pytest.mark.asyncio
async def test_websocket_endpoint_disconnects_on_error(mock_websocket, mock_event_manager):
    """Test that WebSocket endpoint cleans up on disconnect."""
    mock_websocket.receive_text.side_effect = WebSocketDisconnect()

    with patch('api.routers.websocket.event_manager', mock_event_manager):
        await websocket_endpoint(mock_websocket)

    # Verify disconnect was called
    mock_event_manager.disconnect.assert_called_once_with(mock_websocket)


@pytest.mark.asyncio
async def test_websocket_endpoint_uses_global_event_manager(mock_websocket):
    """Test that WebSocket endpoint uses the global event_manager."""
    from core.events import event_manager

    # Create a real EventManager instance
    original_connections = event_manager.active_connections.copy()

    mock_websocket.receive_text.side_effect = WebSocketDisconnect()

    await websocket_endpoint(mock_websocket)

    # Connection should have been attempted (but cleaned up on disconnect)
    # Verify the endpoint interacted with the global manager
    assert event_manager.get_connection_count() == len(original_connections)


@pytest.mark.asyncio
async def test_websocket_endpoint_ignores_client_messages(mock_websocket, mock_event_manager):
    """Test that WebSocket endpoint ignores client messages (just keeps connection alive)."""
    # Send various messages
    messages = ["ping", "random message", '{"type": "test"}', "keepalive"]
    mock_websocket.receive_text.side_effect = messages + [WebSocketDisconnect()]

    with patch('api.routers.websocket.event_manager', mock_event_manager):
        await websocket_endpoint(mock_websocket)

    # Endpoint should not send any responses to client messages
    # (it just keeps the connection alive)
    mock_websocket.send_text.assert_not_called()
    mock_websocket.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_websocket_endpoint_multiple_sequential_connections(mock_event_manager):
    """Test handling multiple connections sequentially."""
    ws1 = MagicMock()
    ws1.accept = AsyncMock()
    ws1.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

    ws2 = MagicMock()
    ws2.accept = AsyncMock()
    ws2.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

    with patch('api.routers.websocket.event_manager', mock_event_manager):
        # Connect first client
        await websocket_endpoint(ws1)

        # Connect second client
        await websocket_endpoint(ws2)

    # Both connections should have been handled
    assert mock_event_manager.connect.call_count == 2
    assert mock_event_manager.disconnect.call_count == 2


@pytest.mark.asyncio
async def test_websocket_endpoint_connection_lifecycle(mock_websocket, mock_event_manager):
    """Test complete connection lifecycle."""
    # Simulate: connect -> receive messages -> disconnect
    mock_websocket.receive_text.side_effect = [
        "ping",
        "keepalive",
        "ping",
        WebSocketDisconnect()
    ]

    with patch('api.routers.websocket.event_manager', mock_event_manager):
        await websocket_endpoint(mock_websocket)

    # Verify complete lifecycle
    mock_event_manager.connect.assert_called_once_with(mock_websocket)
    assert mock_websocket.receive_text.call_count == 4
    mock_event_manager.disconnect.assert_called_once_with(mock_websocket)
