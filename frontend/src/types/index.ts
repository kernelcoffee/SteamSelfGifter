// API Response wrapper as returned by the ApiClient. The backend's error
// envelope carries `error: {code, message, details}` (or FastAPI's `detail`);
// the ApiClient normalizes every error body so `error` is the message string.
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
  entries: number;
  win_chance: number;
  end_time: string | null;
  discovered_at: string;
  entered_at: string | null;
  is_hidden: boolean;
  is_entered: boolean;
  is_wishlist: boolean;
  is_dlc: boolean;
  is_won: boolean;
  won_at: string | null;
  is_safe: boolean | null;
  safety_score: number | null;
  created_at: string;
  updated_at: string;
  // Optional game data from joined Game table
  game_thumbnail?: string | null;
  game_genres?: string[] | null;
  game_review_score?: number | null;
  game_total_reviews?: number | null;
  game_review_summary?: string | null;
  // Last recorded auto-join decision (written by the entry cycle). The label
  // and kind are rendered by the server from the code and detail.
  eligibility_reason: string | null;
  eligibility_detail: EligibilityDetail | null;
  eligibility_checked_at: string | null;
  eligibility_label: string | null;
  eligibility_kind: AutojoinKind | null;
  // Live decision from the saved or previewed policy; present only on the
  // preview, eligible and lens responses (CandidatePreview).
  decision?: AutoJoinDecision;
}

// --- Auto-join engine (served by the backend registry, never mirrored) ---

export type AutojoinPriorityType = 'wishlist' | 'dlc' | 'ending_soon';

export type AutojoinPriorityItem =
  | { type: 'wishlist' }
  | { type: 'dlc' }
  | { type: 'ending_soon'; threshold_minutes: number };

/** Family of a decision code: picks the icon; the text is always the label. */
export type AutojoinKind = 'enter' | 'gate' | 'filter' | 'budget';

/** Small dict of the values behind a decision (actual vs threshold). */
export type EligibilityDetail = Record<string, string | number | null | string[]>;

/** Detail of an enter outcome: which priority matched and which lifted the filters. */
export interface AutoJoinDecisionDetail {
  priority: AutojoinPriorityType | null;
  rank: number;
  lifted_by: AutojoinPriorityType | null;
}

export interface AutoJoinDecision {
  code: string;
  label: string;
  detail: AutoJoinDecisionDetail;
  priority: AutojoinPriorityType | null;
  rank: number;
  lifted_by: AutojoinPriorityType | null;
}

export interface RegistryRule {
  code: string;
  label: string;
}

export interface RegistryFilter extends RegistryRule {
  setting: string | null;
}

export interface RegistryParam {
  name: string;
  min: number;
  max: number;
  default: number;
}

export interface AutojoinPriorityTypeInfo {
  type: AutojoinPriorityType;
  label: string;
  description: string;
  exempt_from_filters: boolean;
  params: RegistryParam[];
}

export interface AutojoinRegistryLimits {
  genre_max_items: number;
  genre_max_length: number;
  max_priority_items: number;
}

/** GET /api/v1/giveaways/registry */
export interface AutojoinRegistry {
  gates: RegistryRule[];
  filters: RegistryFilter[];
  outcomes: RegistryRule[];
  priority_types: AutojoinPriorityTypeInfo[];
  limits: AutojoinRegistryLimits;
}

/** Body of POST /api/v1/giveaways/preview: the seven policy fields. */
export type PolicyPreviewRequest = Pick<
  Settings,
  | 'autojoin_min_price'
  | 'autojoin_min_score'
  | 'autojoin_min_reviews'
  | 'autojoin_max_game_age'
  | 'excluded_genres'
  | 'included_genres'
  | 'autojoin_priorities'
>;

export interface CandidatePreview extends Giveaway {
  decision: AutoJoinDecision;
}

/** POST /api/v1/giveaways/preview and GET /api/v1/giveaways/eligible */
export interface PolicyPreviewResponse {
  candidates: CandidatePreview[];
  count: number;
  pool: number;
  counts: Record<string, number>;
  budget_applied: false;
}

/** GET /api/v1/giveaways/{active,wishlist,dlc}?lens=autojoin */
export interface LensGiveawaysResponse {
  giveaways: CandidatePreview[];
  count: number;
  lens: 'autojoin';
  budget_applied: false;
}

// Entry model
export interface Entry {
  id: number;
  giveaway_id: number;
  points_spent: number;
  entry_type: 'manual' | 'auto' | 'wishlist' | 'dlc';
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
  genres?: string[] | null;
  categories?: string[] | null;
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
  safety_check_enabled: boolean;
  auto_hide_unsafe: boolean;
  autojoin_enabled: boolean;
  autojoin_start_at: number;
  autojoin_stop_at: number;
  autojoin_min_price: number;
  // null = filter off; 0 is a real minimum that still needs Steam data
  autojoin_min_score: number | null;
  autojoin_min_reviews: number | null;
  autojoin_max_game_age: number | null;
  // Ordered entry priorities; list order is entry order
  autojoin_priorities: AutojoinPriorityItem[];
  excluded_genres: string[];
  included_genres: string[];
  scan_interval_minutes: number;
  max_entries_per_cycle: number;
  automation_enabled: boolean;
  max_scan_pages: number;
  entry_delay_min: number;
  entry_delay_max: number;
  log_retention_days: number;
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

// Distinct genres across cached games (GET /api/v1/games/genres)
export interface GenreCount {
  name: string;
  count: number;
}

export interface GenreList {
  genres: GenreCount[];
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
  wishlist_new?: number;
  wishlist_updated?: number;
  dlc_new?: number;
  dlc_updated?: number;
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
