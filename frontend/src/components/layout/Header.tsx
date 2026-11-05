import type { Ref } from 'react';
import { Sun, Moon, Activity, Wifi, WifiOff, UserCheck, UserX, Menu, X } from 'lucide-react';
import { useThemeStore } from '@/stores/themeStore';
import { useSessionStatus, useWebSocketStatus } from '@/hooks';

interface HeaderProps {
  schedulerRunning?: boolean;
  schedulerPaused?: boolean;
  /** Phone-width menu: shown below the md breakpoint when a toggle is given. */
  menuOpen?: boolean;
  menuId?: string;
  menuButtonRef?: Ref<HTMLButtonElement>;
  onMenuToggle?: () => void;
}

/**
 * Application header with logo, scheduler status, and theme toggle
 */
export function Header({
  schedulerRunning = false,
  schedulerPaused = false,
  menuOpen = false,
  menuId,
  menuButtonRef,
  onMenuToggle,
}: HeaderProps) {
  const { isDark, toggle } = useThemeStore();
  const { isConnected } = useWebSocketStatus();
  const { data: session } = useSessionStatus();

  let sessionTitle = 'SteamGifts session not configured';
  if (session?.configured && session.valid) {
    sessionTitle = session.username
      ? `Connected to SteamGifts as ${session.username}`
      : 'Connected to SteamGifts';
  } else if (session?.configured) {
    sessionTitle = 'SteamGifts session invalid or expired — update it in Settings';
  }

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
    // Sticky above the phone menu overlay (z-40) so the toggle that opened the
    // menu stays the topmost control; static from md up, as before.
    <header className="sticky top-0 z-50 md:static md:z-auto h-16 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-surface-dark px-4 md:px-6">
      <div className="h-full flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          {onMenuToggle && (
            <button
              ref={menuButtonRef}
              type="button"
              onClick={onMenuToggle}
              aria-expanded={menuOpen}
              aria-controls={menuOpen ? menuId : undefined}
              aria-label={menuOpen ? 'Close menu' : 'Open menu'}
              className="md:hidden p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300"
            >
              {menuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          )}
          {/* Logo/Title */}
          <h1 className="truncate text-xl font-bold text-gray-900 dark:text-white">
            SteamSelfGifter
          </h1>
        </div>

        <div className="flex shrink-0 items-center gap-2 sm:gap-4">
          {/* SteamGifts Session Indicator */}
          {session && (
            <div className="flex items-center gap-1" title={sessionTitle}>
              {session.configured && session.valid ? (
                <UserCheck className="text-green-500" size={16} aria-label={sessionTitle} />
              ) : (
                <UserX
                  className={session.configured ? 'text-red-500' : 'text-gray-400'}
                  size={16}
                  aria-label={sessionTitle}
                />
              )}
            </div>
          )}

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
