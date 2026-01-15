import { createContext } from 'react';

export interface WebSocketContextValue {
  isConnected: boolean;
  reconnect: () => void;
}

export const WebSocketContext = createContext<WebSocketContextValue>({
  isConnected: false,
  reconnect: () => {},
});