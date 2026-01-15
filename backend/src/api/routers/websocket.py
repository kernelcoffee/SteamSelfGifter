"""WebSocket router for real-time client notifications.

This module provides WebSocket endpoints for establishing real-time
bidirectional communication between the server and web clients.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from core.events import event_manager


router = APIRouter()


@router.websocket("/events")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time event streaming.

    This endpoint accepts WebSocket connections and keeps them alive,
    allowing the server to push real-time updates to connected clients.
    The connection is maintained until the client disconnects.

    Events are broadcast via the global EventManager instance, which
    handles connection management and event distribution.

    Connection Flow:
        1. Client connects to ws://host/ws/events
        2. Server accepts connection and registers it
        3. Server can broadcast events to all connected clients
        4. Client can send keepalive messages (ignored by server)
        5. On disconnect, server automatically unregisters connection

    Event Types:
        - notification: User-facing notifications (info, warning, error)
        - stats_update: Statistics updates (points, entries, etc.)
        - scan_progress: Real-time scan progress updates
        - scan_complete: Scan completion notification
        - entry_success: Successful giveaway entry
        - entry_failure: Failed giveaway entry

    Example Client Code (JavaScript):
        ```javascript
        const ws = new WebSocket('ws://localhost:8000/ws/events');

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('Event:', data.type, data.data);
            console.log('Timestamp:', data.timestamp);

            switch(data.type) {
                case 'notification':
                    showNotification(data.data.level, data.data.message);
                    break;
                case 'stats_update':
                    updateStats(data.data);
                    break;
                case 'scan_progress':
                    updateProgress(data.data.current_page, data.data.total_pages);
                    break;
            }
        };

        ws.onopen = () => console.log('Connected to WebSocket');
        ws.onclose = () => console.log('Disconnected from WebSocket');
        ws.onerror = (error) => console.error('WebSocket error:', error);

        // Optional: Send keepalive messages
        setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({type: 'ping'}));
            }
        }, 30000);
        ```

    Args:
        websocket: WebSocket connection from FastAPI

    Raises:
        WebSocketDisconnect: When client disconnects (handled gracefully)

    Example Event (JSON):
        {
            "type": "notification",
            "data": {
                "level": "info",
                "message": "Entered giveaway for Portal 2",
                "details": {"points": 50}
            },
            "timestamp": "2024-01-15T10:30:45.123456"
        }
    """
    # Accept and register the WebSocket connection
    await event_manager.connect(websocket)

    try:
        # Keep connection alive and handle incoming messages
        # Note: We don't currently process client messages, but we need to
        # receive them to keep the connection alive and detect disconnects
        while True:
            # Wait for messages from client (e.g., keepalive pings)
            # This also allows us to detect when the client disconnects
            data = await websocket.receive_text()

            # We could process client messages here if needed in the future
            # For now, we just ignore them (they're just keepalive messages)
            # Example: Handle ping/pong
            # if data == "ping":
            #     await websocket.send_text("pong")

    except WebSocketDisconnect:
        # Client disconnected - clean up the connection
        event_manager.disconnect(websocket)
