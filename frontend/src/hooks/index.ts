// Settings hooks
export {
  useSettings,
  useUpdateSettings,
  useValidateConfig,
  useTestSession,
  settingsKeys,
} from './useSettings';

// Scheduler hooks
export {
  useSchedulerStatus,
  useStartScheduler,
  useStopScheduler,
  usePauseScheduler,
  useResumeScheduler,
  useTriggerScan,
  useTriggerProcess,
  useSchedulerControl,
  schedulerKeys,
} from './useScheduler';

// Giveaway hooks
export {
  useGiveaways,
  useInfiniteGiveaways,
  useGiveaway,
  useEnterGiveaway,
  useHideGiveaway,
  useUnhideGiveaway,
  useRemoveEntry,
  useRefreshGiveawayGame,
  useCheckGiveawaySafety,
  useHideOnSteamGifts,
  usePostComment,
  giveawayKeys,
  type GiveawayFilters,
} from './useGiveaways';

// Entry hooks
export {
  useEntries,
  useEntry,
  useHistory,
  entryKeys,
  type EntryFilters,
} from './useEntries';

// Analytics hooks
export {
  useDashboard,
  useEntryStats,
  useGiveawayStats,
  useGameStats,
  useEntryTrends,
  analyticsKeys,
  type TimeRangeFilter,
  type TrendDataPoint,
} from './useAnalytics';

// Log hooks
export {
  useLogs,
  useClearLogs,
  useExportLogs,
  logKeys,
  type LogFilters,
} from './useLogs';

// Game hooks
export {
  useGames,
  useGame,
  useRefreshGame,
  useRefreshStaleGames,
  gameKeys,
  type GameFilters,
} from './useGames';

// System hooks
export {
  useHealthCheck,
  useSystemInfo,
  systemKeys,
} from './useSystem';

// WebSocket hooks
export {
  useWebSocket,
  useWebSocketConnection,
  useWebSocketEvent,
  useWebSocketAnyEvent,
  useWebSocketNotifications,
  useWebSocketQueryInvalidation,
  useScanProgress,
} from './useWebSocket';

// WebSocket status hook (for accessing provider context)
export { useWebSocketStatus } from './useWebSocketStatus';
