/**
 * WebSocket service for real-time event streaming
 *
 * Connects to backend WebSocket endpoint and provides
 * event handling for real-time updates.
 */

import type { WebSocketEvent } from '@/types';

type EventHandler = (event: WebSocketEvent) => void;
type ConnectionHandler = () => void;

interface WebSocketServiceOptions {
  url?: string;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  keepaliveInterval?: number;
}

class WebSocketService {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectInterval: number;
  private maxReconnectAttempts: number;
  private keepaliveInterval: number;
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private keepaliveTimer: ReturnType<typeof setInterval> | null = null;
  private eventHandlers: Map<string, Set<EventHandler>> = new Map();
  private globalHandlers: Set<EventHandler> = new Set();
  private onConnectHandlers: Set<ConnectionHandler> = new Set();
  private onDisconnectHandlers: Set<ConnectionHandler> = new Set();
  private isIntentionallyClosed = false;

  constructor(options: WebSocketServiceOptions = {}) {
    // Default to relative WebSocket URL for same-origin connection
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.url = options.url || `${wsProtocol}//${window.location.host}/ws/events`;
    this.reconnectInterval = options.reconnectInterval || 3000;
    this.maxReconnectAttempts = options.maxReconnectAttempts || 10;
    this.keepaliveInterval = options.keepaliveInterval || 30000;
  }

  /**
   * Connect to the WebSocket server
   */
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    this.isIntentionallyClosed = false;

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log('[WebSocket] Connected to', this.url);
        this.reconnectAttempts = 0;
        this.startKeepalive();
        this.onConnectHandlers.forEach(handler => handler());
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WebSocketEvent;
          this.handleEvent(data);
        } catch (err) {
          console.error('[WebSocket] Failed to parse message:', err);
        }
      };

      this.ws.onclose = (event) => {
        console.log('[WebSocket] Disconnected:', event.code, event.reason);
        this.stopKeepalive();
        this.onDisconnectHandlers.forEach(handler => handler());

        if (!this.isIntentionallyClosed) {
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
      };
    } catch (err) {
      console.error('[WebSocket] Failed to connect:', err);
      this.scheduleReconnect();
    }
  }

  /**
   * Disconnect from the WebSocket server
   */
  disconnect(): void {
    this.isIntentionallyClosed = true;
    this.stopKeepalive();
    this.clearReconnectTimer();

    if (this.ws) {
      this.ws.close(1000, 'Client disconnecting');
      this.ws = null;
    }
  }

  /**
   * Subscribe to a specific event type
   */
  on(eventType: string, handler: EventHandler): () => void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, new Set());
    }
    this.eventHandlers.get(eventType)!.add(handler);

    // Return unsubscribe function
    return () => {
      this.eventHandlers.get(eventType)?.delete(handler);
    };
  }

  /**
   * Subscribe to all events
   */
  onAny(handler: EventHandler): () => void {
    this.globalHandlers.add(handler);
    return () => {
      this.globalHandlers.delete(handler);
    };
  }

  /**
   * Subscribe to connection events
   */
  onConnect(handler: ConnectionHandler): () => void {
    this.onConnectHandlers.add(handler);
    return () => {
      this.onConnectHandlers.delete(handler);
    };
  }

  /**
   * Subscribe to disconnection events
   */
  onDisconnect(handler: ConnectionHandler): () => void {
    this.onDisconnectHandlers.add(handler);
    return () => {
      this.onDisconnectHandlers.delete(handler);
    };
  }

  /**
   * Check if connected
   */
  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /**
   * Send a message to the server
   */
  send(data: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  private handleEvent(event: WebSocketEvent): void {
    // Call global handlers
    this.globalHandlers.forEach(handler => {
      try {
        handler(event);
      } catch (err) {
        console.error('[WebSocket] Handler error:', err);
      }
    });

    // Call type-specific handlers
    const handlers = this.eventHandlers.get(event.type);
    if (handlers) {
      handlers.forEach(handler => {
        try {
          handler(event);
        } catch (err) {
          console.error('[WebSocket] Handler error:', err);
        }
      });
    }
  }

  private startKeepalive(): void {
    this.stopKeepalive();
    this.keepaliveTimer = setInterval(() => {
      this.send({ type: 'ping' });
    }, this.keepaliveInterval);
  }

  private stopKeepalive(): void {
    if (this.keepaliveTimer) {
      clearInterval(this.keepaliveTimer);
      this.keepaliveTimer = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('[WebSocket] Max reconnect attempts reached');
      return;
    }

    this.clearReconnectTimer();
    this.reconnectAttempts++;

    const delay = this.reconnectInterval * Math.min(this.reconnectAttempts, 5);
    console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}

// Create singleton instance
export const websocketService = new WebSocketService();

// Export class for testing
export { WebSocketService };
