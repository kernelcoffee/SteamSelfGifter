/**
 * Hook to access WebSocket connection state
 */

import { useContext } from 'react';
import { WebSocketContext } from '@/components/providers/WebSocketContext';

export function useWebSocketStatus() {
  return useContext(WebSocketContext);
}