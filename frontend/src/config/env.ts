// Environment configuration
// In development, Vite proxies /api and /ws to the backend
// In production, these would be the actual URLs

export const config = {
  // API base URL (empty in dev because of Vite proxy)
  apiUrl: import.meta.env.VITE_API_URL || '',

  // WebSocket URL
  wsUrl: import.meta.env.VITE_WS_URL || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`,

  // App info
  appName: 'SteamSelfGifter',
  version: '2.0.0',
} as const;
