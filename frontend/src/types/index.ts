// API Response wrapper - all backend responses have this shape
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  error?: string;
}

// Giveaway model
export interface Giveaway {
  id: number;
  code: string;
  url: string;
  game_name: string;
  game_id: number | null;
  price: number;
  copies: number;
  end_time: string | null;
  discovered_at: string;
  entered_at: string | null;
  is_hidden: boolean;
  is_entered: boolean;
  is_wishlist: boolean;
  is_won: boolean;
  won_at: string | null;
  is_safe: boolean | null;
  safety_score: number | null;
  created_at: string;
  updated_at: string;
  // Optional game data from joined Game table
  game_thumbnail?: string | null;
  game_review_score?: number | null;
  game_total_reviews?: number | null;
  game_review_summary?: string | null;
}

// Entry model
export interface Entry {
  id: number;
  giveaway_id: number;
  points_spent: number;
  entry_type: 'manual' | 'auto' | 'wishlist';
  status: 'success' | 'failed' | 'pending';
  entered_at: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

// Entry with giveaway info for history
export interface EntryWithGiveaway extends Entry {
  giveaway: Giveaway;
}

// Game model
export interface Game {
  id: number;
  name: string;
  type: 'game' | 'dlc' | 'bundle';
  release_date: string | null;
  review_score: number | null;
  total_positive: number | null;
  total_negative: number | null;
  total_reviews: number | null;
  is_bundle: boolean;
  bundle_content: string | null;
  game_id: number | null;
  description: string | null;
  price: number | null;
  last_refreshed_at: string | null;
  created_at: string;
  updated_at: string;
}

// Safety check result
export interface SafetyCheckResult {
  is_safe: boolean;
  safety_score: number;
  bad_count: number;
  good_count: number;
  net_bad: number;
  details: string[];
}

// Settings model
export interface Settings {
  id: number;
  phpsessid: string | null;
  user_agent: string;
  xsrf_token: string | null;
  dlc_enabled: boolean;
  safety_check_enabled: boolean;
  auto_hide_unsafe: boolean;
  autojoin_enabled: boolean;
  autojoin_start_at: number;
  autojoin_stop_at: number;
  autojoin_min_price: number;
  autojoin_min_score: number;
  autojoin_min_reviews: number;
  autojoin_max_game_age: number | null;
  scan_interval_minutes: number;
  max_entries_per_cycle: number;
  automation_enabled: boolean;
  max_scan_pages: number;
  entry_delay_min: number;
  entry_delay_max: number;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

// Scheduler status
export interface SchedulerStatus {
  running: boolean;
  paused: boolean;
  job_count: number;
  jobs: SchedulerJob[];
}

export interface SchedulerJob {
  id: string;
  name: string;
  next_run: string | null;
  pending: boolean;
}

// Analytics types
export interface EntryStats {
  total: number;
  successful: number;
  failed: number;
  total_points_spent: number;
  success_rate: number;
  by_type: {
    manual: number;
    auto: number;
    wishlist: number;
  };
}

export interface GiveawayStats {
  total: number;
  active: number;
  entered: number;
  hidden: number;
  wins: number;
  win_rate: number;
}

export interface GameStats {
  total_games: number;
  games: number;
  dlc: number;
  bundles: number;
  stale_games: number;
}

export interface DashboardData {
  session: {
    configured: boolean;
    valid: boolean;
    username: string | null;
    error: string | null;
  };
  points: {
    current: number | null;
  };
  entries: {
    total: number;
    today: number;
    entered_30d: number;
    wins_30d: number;
    win_rate: number;
  };
  giveaways: {
    active: number;
    entered: number;
    wins: number;
  };
  safety: {
    checked: number;
    safe: number;
    unsafe: number;
    unchecked: number;
  };
  scheduler: {
    running: boolean;
    paused: boolean;
    last_scan: string | null;
    next_scan: string | null;
  };
}

// Activity log
export interface ActivityLog {
  id: number;
  level: 'info' | 'warning' | 'error';
  event_type: 'scan' | 'entry' | 'error' | 'config' | 'scheduler';
  message: string;
  details: string | null;
  created_at: string;
}

// System info
export interface SystemInfo {
  app_name: string;
  version: string;
  debug: boolean;
  database: string;
}

export interface HealthCheck {
  status: string;
  timestamp: string;
  version: string;
}

// Scan result
export interface ScanResult {
  new: number;
  updated: number;
  pages_scanned: number;
  scan_time: number;
  skipped?: boolean;
  reason?: string;
}

// Process result
export interface ProcessResult {
  eligible: number;
  entered: number;
  failed: number;
  points_spent: number;
  skipped?: boolean;
  reason?: string;
}

// Win sync result
export interface WinSyncResult {
  new_wins: number;
  skipped?: boolean;
  reason?: string;
}

// Automation cycle result
export interface AutomationCycleResult {
  scan: {
    new: number;
    updated: number;
    pages?: number;
    skipped: boolean;
    error?: string;
  };
  wishlist: {
    new: number;
    updated: number;
    skipped: boolean;
    error?: string;
  };
  wins: {
    new_wins: number;
    skipped: boolean;
    error?: string;
  };
  entries: {
    eligible: number;
    entered: number;
    failed: number;
    points_spent: number;
    skipped: boolean;
    reason?: string;
    error?: string;
  };
  cycle_time: number;
  skipped?: boolean;
  reason?: string;
}

// Configuration validation
export interface ConfigValidation {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
}

// WebSocket event
export interface WebSocketEvent<T = unknown> {
  type: string;
  data: T;
  timestamp: string;
}
