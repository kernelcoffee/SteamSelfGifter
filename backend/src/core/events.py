"""WebSocket event manager for real-time client notifications.

This module provides the EventManager class for broadcasting events to
connected WebSocket clients, enabling real-time updates in the web UI.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Set
from fastapi import WebSocket


class EventManager:
    """
    Manages WebSocket connections and broadcasts events to connected clients.

    This class provides a centralized event broadcasting system for real-time
    notifications to the web UI. It maintains a set of active WebSocket
    connections and provides methods to broadcast events to all or specific clients.

    Design Notes:
        - Thread-safe using asyncio primitives
        - Automatically removes disconnected clients
        - Events are JSON-serialized before sending
        - Supports both broadcast (all clients) and targeted (specific client) events
        - Gracefully handles client disconnections during broadcast

    Usage:
        >>> manager = EventManager()
        >>> # In WebSocket endpoint:
        >>> await manager.connect(websocket)
        >>> try:
        ...     # Keep connection alive
        ...     while True:
        ...         await websocket.receive_text()
        >>> finally:
        ...     manager.disconnect(websocket)
        >>>
        >>> # Broadcasting events:
        >>> await manager.broadcast_event("scan_complete", {"new": 5, "updated": 3})

    Attributes:
        active_connections: Set of currently connected WebSocket clients
    """

    def __init__(self):
        """Initialize EventManager with empty connection set."""
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept and register a new WebSocket connection.

        Args:
            websocket: WebSocket connection to accept and register

        Example:
            >>> await manager.connect(websocket)
        """
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """
        Unregister a WebSocket connection.

        This should be called when a client disconnects or when an error occurs.

        Args:
            websocket: WebSocket connection to unregister

        Example:
            >>> manager.disconnect(websocket)
        """
        self.active_connections.discard(websocket)

    async def send_event(self, websocket: WebSocket, event: Dict[str, Any]) -> None:
        """
        Send an event to a specific WebSocket client.

        Args:
            websocket: Target WebSocket connection
            event: Event data to send (will be JSON-serialized)

        Raises:
            Exception: If sending fails (connection closed, etc.)

        Example:
            >>> event = {"type": "entry_success", "data": {"game": "Portal 2"}}
            >>> await manager.send_event(websocket, event)
        """
        await websocket.send_json(event)

    async def broadcast_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Broadcast an event to all connected WebSocket clients.

        Creates a standardized event structure and sends it to all active connections.
        Automatically removes clients that fail to receive the event (disconnected).

        Args:
            event_type: Type of event (e.g., "scan_complete", "entry_success")
            data: Event payload data

        Event Structure:
            {
                "type": event_type,
                "data": data,
                "timestamp": ISO timestamp
            }

        Example:
            >>> await manager.broadcast_event(
            ...     "scan_complete",
            ...     {"new_giveaways": 5, "updated_giveaways": 3}
            ... )
        """
        if not self.active_connections:
            return  # No clients to broadcast to

        # Create event structure
        event = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Track disconnected clients for removal
        disconnected = set()

        # Broadcast to all clients
        for websocket in self.active_connections:
            try:
                await self.send_event(websocket, event)
            except Exception:
                # Client disconnected or error occurred
                disconnected.add(websocket)

        # Remove disconnected clients
        for websocket in disconnected:
            self.disconnect(websocket)

    async def broadcast_notification(
        self,
        level: str,
        message: str,
        details: Dict[str, Any] | None = None,
    ) -> None:
        """
        Broadcast a notification message to all connected clients.

        Convenience method for sending user-facing notifications.

        Args:
            level: Notification level - "info", "warning", or "error"
            message: Human-readable notification message
            details: Optional additional details

        Example:
            >>> await manager.broadcast_notification(
            ...     "info",
            ...     "Entered giveaway for Portal 2",
            ...     {"points": 50}
            ... )
        """
        await self.broadcast_event(
            "notification",
            {
                "level": level,
                "message": message,
                "details": details or {},
            },
        )

    def get_connection_count(self) -> int:
        """
        Get the number of active WebSocket connections.

        Returns:
            Number of currently connected clients

        Example:
            >>> count = manager.get_connection_count()
            >>> print(f"Active connections: {count}")
        """
        return len(self.active_connections)

    async def broadcast_stats_update(self, stats: Dict[str, Any]) -> None:
        """
        Broadcast statistics update to all connected clients.

        Convenience method for sending statistics updates (points, entries, etc.).

        Args:
            stats: Statistics data to broadcast

        Example:
            >>> await manager.broadcast_stats_update({
            ...     "current_points": 450,
            ...     "total_entries": 23,
            ...     "active_giveaways": 142
            ... })
        """
        await self.broadcast_event("stats_update", stats)

    async def broadcast_scan_progress(
        self,
        current_page: int,
        total_pages: int,
        found: int,
    ) -> None:
        """
        Broadcast scan progress update to all connected clients.

        Convenience method for sending real-time scan progress.

        Args:
            current_page: Current page being scanned
            total_pages: Total number of pages to scan
            found: Number of giveaways found so far

        Example:
            >>> await manager.broadcast_scan_progress(
            ...     current_page=2,
            ...     total_pages=3,
            ...     found=15
            ... )
        """
        await self.broadcast_event(
            "scan_progress",
            {
                "current_page": current_page,
                "total_pages": total_pages,
                "found": found,
            },
        )

    async def broadcast_session_invalid(
        self,
        reason: str,
        error_code: str | None = None,
    ) -> None:
        """
        Broadcast session invalid notification to all connected clients.

        This notifies the frontend that the SteamGifts session has expired
        or become invalid, prompting the user to update their credentials.

        Args:
            reason: Human-readable reason for invalidation
            error_code: Optional error code (e.g., "SG_004")

        Example:
            >>> await manager.broadcast_session_invalid(
            ...     reason="Session expired - please update your PHPSESSID",
            ...     error_code="SG_004"
            ... )
        """
        await self.broadcast_event(
            "session_invalid",
            {
                "reason": reason,
                "error_code": error_code,
            },
        )


# Global event manager instance
# This singleton is used throughout the application
event_manager = EventManager()
