import { Sun, Moon, Activity, Wifi, WifiOff } from 'lucide-react';
import { useThemeStore } from '@/stores/themeStore';
import { useWebSocketStatus } from '@/hooks';

interface HeaderProps {
  schedulerRunning?: boolean;
  schedulerPaused?: boolean;
}

/**
 * Application header with logo, scheduler status, and theme toggle
 */
export function Header({ schedulerRunning = false, schedulerPaused = false }: HeaderProps) {
  const { isDark, toggle } = useThemeStore();
  const { isConnected } = useWebSocketStatus();

  // Determine status color and text
  let statusColor = 'text-gray-400';
  let statusText = 'Stopped';

  if (schedulerRunning) {
    if (schedulerPaused) {
      statusColor = 'text-yellow-500';
      statusText = 'Paused';
    } else {
      statusColor = 'text-green-500';
      statusText = 'Running';
    }
  }

  return (
    <header className="h-16 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-surface-dark px-6">
      <div className="h-full flex items-center justify-between">
        {/* Logo/Title */}
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">
          SteamSelfGifter
        </h1>

        <div className="flex items-center gap-4">
          {/* WebSocket Connection Indicator */}
          <div
            className="flex items-center gap-1"
            title={isConnected ? 'Real-time updates connected' : 'Real-time updates disconnected'}
          >
            {isConnected ? (
              <Wifi className="text-green-500" size={16} />
            ) : (
              <WifiOff className="text-gray-400" size={16} />
            )}
          </div>

          {/* Scheduler Status Indicator */}
          <div className="flex items-center gap-2">
            <Activity className={statusColor} size={20} />
            <span className={`text-sm font-medium ${statusColor}`}>
              {statusText}
            </span>
          </div>

          {/* Theme Toggle Button */}
          <button
            onClick={toggle}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300 transition-colors"
            aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {isDark ? <Sun size={20} /> : <Moon size={20} />}
          </button>
        </div>
      </div>
    </header>
  );
}
