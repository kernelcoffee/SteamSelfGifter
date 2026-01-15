/**
 * WebSocket Provider Component
 *
 * Initializes WebSocket connection and real-time event handling.
 * Should be placed inside QueryClientProvider.
 */

import { type ReactNode } from 'react';
import { useWebSocket } from '@/hooks';
import { WebSocketContext } from './WebSocketContext';

interface WebSocketProviderProps {
  children: ReactNode;
}

/**
 * Provider component that manages WebSocket connection
 *
 * Wraps children with WebSocket context and enables:
 * - Automatic connection management
 * - Real-time notifications
 * - Query cache invalidation on events
 */
export function WebSocketProvider({ children }: WebSocketProviderProps) {
  const { isConnected, reconnect } = useWebSocket();

  return (
    <WebSocketContext.Provider value={{ isConnected, reconnect }}>
      {children}
    </WebSocketContext.Provider>
  );
}