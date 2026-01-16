/**
 * React hooks for WebSocket integration
 *
 * Provides easy access to real-time events in React components.
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { websocketService } from '@/services/websocket';
import { showSuccess, showError, showWarning, showInfo } from '@/stores/uiStore';
import type { WebSocketEvent } from '@/types';

/**
 * Hook to manage WebSocket connection lifecycle
 *
 * Automatically connects on mount and disconnects on unmount.
 * Only one component should use this hook (typically at the app root).
 */
export function useWebSocketConnection() {
  const [isConnected, setIsConnected] = useState(websocketService.isConnected);

  useEffect(() => {
    const unsubConnect = websocketService.onConnect(() => {
      setIsConnected(true);
    });

    const unsubDisconnect = websocketService.onDisconnect(() => {
      setIsConnected(false);
    });

    // Connect on mount
    websocketService.connect();

    return () => {
      unsubConnect();
      unsubDisconnect();
      // Note: We don't disconnect here because other components may still need it
      // The connection will be cleaned up when the page unloads
    };
  }, []);

  const reconnect = useCallback(() => {
    websocketService.disconnect();
    websocketService.connect();
  }, []);

  return { isConnected, reconnect };
}

/**
 * Hook to subscribe to specific WebSocket event types
 *
 * @param eventType - The event type to subscribe to
 * @param handler - Callback function when event is received
 */
export function useWebSocketEvent<T = unknown>(
  eventType: string,
  handler: (data: T, event: WebSocketEvent<T>) => void
) {
  const handlerRef = useRef(handler);

  useEffect(() => {
    handlerRef.current = handler;
  });

  useEffect(() => {
    const unsubscribe = websocketService.on(eventType, (event) => {
      handlerRef.current(event.data as T, event as WebSocketEvent<T>);
    });

    return unsubscribe;
  }, [eventType]);
}

/**
 * Hook to subscribe to all WebSocket events
 *
 * @param handler - Callback function when any event is received
 */
export function useWebSocketAnyEvent(handler: (event: WebSocketEvent) => void) {
  const handlerRef = useRef(handler);

  useEffect(() => {
    handlerRef.current = handler;
  });

  useEffect(() => {
    const unsubscribe = websocketService.onAny((event) => {
      handlerRef.current(event);
    });

    return unsubscribe;
  }, []);
}

/**
 * Notification data from WebSocket
 */
interface NotificationData {
  level: 'info' | 'warning' | 'error' | 'success';
  message: string;
  details?: Record<string, unknown>;
}

/**
 * Hook that automatically handles WebSocket notifications
 *
 * Displays toast notifications for incoming WebSocket notification events.
 */
export function useWebSocketNotifications() {
  useWebSocketEvent<NotificationData>('notification', (data) => {
    switch (data.level) {
      case 'success':
        showSuccess(data.message);
        break;
      case 'error':
        showError(data.message);
        break;
      case 'warning':
        showWarning(data.message);
        break;
      case 'info':
      default:
        showInfo(data.message);
        break;
    }
  });
}

/**
 * Stats update data from WebSocket
 */
interface StatsUpdateData {
  points?: number;
  active_giveaways?: number;
  entries_today?: number;
}

/**
 * Session invalid data from WebSocket
 */
interface SessionInvalidData {
  reason: string;
  error_code?: string;
}

/**
 * Hook that automatically invalidates React Query cache on stats updates
 *
 * Ensures UI stays in sync with real-time data changes.
 */
export function useWebSocketQueryInvalidation() {
  const queryClient = useQueryClient();

  // Invalidate dashboard on stats update
  useWebSocketEvent<StatsUpdateData>('stats_update', () => {
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
  });

  // Invalidate scheduler status on scheduler events
  useWebSocketEvent('scheduler_started', () => {
    queryClient.invalidateQueries({ queryKey: ['scheduler'] });
  });

  useWebSocketEvent('scheduler_stopped', () => {
    queryClient.invalidateQueries({ queryKey: ['scheduler'] });
  });

  useWebSocketEvent('scheduler_paused', () => {
    queryClient.invalidateQueries({ queryKey: ['scheduler'] });
  });

  useWebSocketEvent('scheduler_resumed', () => {
    queryClient.invalidateQueries({ queryKey: ['scheduler'] });
  });

  // Invalidate giveaways on scan complete
  useWebSocketEvent('scan_complete', () => {
    queryClient.invalidateQueries({ queryKey: ['giveaways'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
  });

  // Invalidate entries on entry events
  useWebSocketEvent('entry_success', () => {
    queryClient.invalidateQueries({ queryKey: ['entries'] });
    queryClient.invalidateQueries({ queryKey: ['giveaways'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    queryClient.invalidateQueries({ queryKey: ['analytics'] });
  });

  useWebSocketEvent('entry_failure', () => {
    queryClient.invalidateQueries({ queryKey: ['entries'] });
    queryClient.invalidateQueries({ queryKey: ['analytics'] });
  });

  // Invalidate logs on new log entry
  useWebSocketEvent('log_entry', () => {
    queryClient.invalidateQueries({ queryKey: ['logs'] });
  });

  // Handle session invalid event
  useWebSocketEvent<SessionInvalidData>('session_invalid', (data) => {
    // Invalidate dashboard to update session status banner
    queryClient.invalidateQueries({ queryKey: ['analytics', 'dashboard'] });
    // Show warning notification
    showWarning(data.reason || 'Your SteamGifts session has expired. Please update your PHPSESSID in Settings.');
  });
}

/**
 * Scan progress data from WebSocket
 */
interface ScanProgressData {
  current_page: number;
  total_pages: number;
  new_giveaways: number;
}

/**
 * Hook to track scan progress
 *
 * Returns current scan progress state.
 */
export function useScanProgress() {
  const [progress, setProgress] = useState<ScanProgressData | null>(null);
  const [isScanning, setIsScanning] = useState(false);

  useWebSocketEvent<ScanProgressData>('scan_progress', (data) => {
    setProgress(data);
    setIsScanning(true);
  });

  useWebSocketEvent('scan_complete', () => {
    setProgress(null);
    setIsScanning(false);
  });

  useWebSocketEvent('scan_error', () => {
    setProgress(null);
    setIsScanning(false);
  });

  return { progress, isScanning };
}

/**
 * Combined hook for all WebSocket functionality
 *
 * Use this at the app root to enable all real-time features.
 */
export function useWebSocket() {
  const connection = useWebSocketConnection();

  // Enable notifications
  useWebSocketNotifications();

  // Enable query invalidation
  useWebSocketQueryInvalidation();

  return connection;
}
