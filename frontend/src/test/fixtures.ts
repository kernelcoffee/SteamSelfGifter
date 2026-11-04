import type { AutojoinRegistry, Giveaway, PolicyPreviewResponse, Settings } from '@/types';

/** Registry exactly as GET /api/v1/giveaways/registry serves it (contract). */
export const testRegistry: AutojoinRegistry = {
  gates: [
    { code: 'expired', label: 'Giveaway has ended' },
    { code: 'hidden', label: 'Hidden' },
    { code: 'entered', label: 'Already entered' },
    { code: 'unsafe', label: 'Flagged unsafe or borderline by the safety check' },
  ],
  filters: [
    { code: 'price_below_min', label: 'Price below minimum', setting: 'autojoin_min_price' },
    { code: 'genre_excluded', label: 'Game genre is excluded', setting: 'excluded_genres' },
    { code: 'genre_not_included', label: 'No genre on your included list', setting: 'included_genres' },
    { code: 'no_game_data', label: 'No Steam game data cached', setting: null },
    { code: 'score_below_min', label: 'Review score below minimum', setting: 'autojoin_min_score' },
    { code: 'reviews_below_min', label: 'Too few reviews', setting: 'autojoin_min_reviews' },
    {
      code: 'game_too_old',
      label: 'Game older than allowed (or release date unknown)',
      setting: 'autojoin_max_game_age',
    },
  ],
  outcomes: [
    { code: 'eligible', label: 'Joinable' },
    { code: 'budget_floor', label: 'Not entered last cycle: points floor' },
    { code: 'cycle_cap', label: 'Not entered last cycle: per cycle cap' },
    { code: 'points_accumulating', label: 'Not entered last cycle: accumulating points' },
  ],
  priority_types: [
    {
      type: 'wishlist',
      label: 'Wishlist',
      description: 'Games on your Steam wishlist',
      exempt_from_filters: true,
      params: [],
    },
    {
      type: 'dlc',
      label: 'DLC',
      description: 'DLC for games you own, from the DLC listing',
      exempt_from_filters: true,
      params: [],
    },
    {
      type: 'ending_soon',
      label: 'Ending soon',
      description: 'Giveaways ending within the threshold, soonest first',
      exempt_from_filters: false,
      params: [{ name: 'threshold_minutes', min: 5, max: 10080, default: 60 }],
    },
  ],
  limits: { genre_max_items: 50, genre_max_length: 64, max_priority_items: 3 },
};

export const testSettings: Settings = {
  id: 1,
  phpsessid: 'test-session-id',
  user_agent: 'test-user-agent',
  xsrf_token: null,
  safety_check_enabled: true,
  auto_hide_unsafe: true,
  autojoin_enabled: true,
  autojoin_start_at: 350,
  autojoin_stop_at: 200,
  autojoin_min_price: 10,
  autojoin_min_score: 7,
  autojoin_min_reviews: 1000,
  autojoin_max_game_age: null,
  autojoin_priorities: [{ type: 'wishlist' }],
  excluded_genres: [],
  included_genres: [],
  scan_interval_minutes: 30,
  max_entries_per_cycle: 10,
  automation_enabled: true,
  max_scan_pages: 3,
  entry_delay_min: 8,
  entry_delay_max: 12,
  log_retention_days: 30,
  last_synced_at: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

export function makeGiveaway(over: Partial<Giveaway> = {}): Giveaway {
  return {
    id: 1,
    code: 'AbC12',
    url: 'https://www.steamgifts.com/giveaway/AbC12/',
    game_name: 'Hollow Knight',
    game_id: 367520,
    price: 15,
    copies: 1,
    entries: 120,
    win_chance: 0.8,
    end_time: new Date(Date.now() + 3_600_000).toISOString(),
    discovered_at: '2026-01-01T00:00:00Z',
    entered_at: null,
    is_hidden: false,
    is_entered: false,
    is_wishlist: false,
    is_dlc: false,
    is_won: false,
    won_at: null,
    is_safe: true,
    safety_score: 95,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    game_thumbnail: null,
    eligibility_reason: null,
    eligibility_detail: null,
    eligibility_checked_at: null,
    eligibility_label: null,
    eligibility_kind: null,
    ...over,
  };
}

export function makePreview(over: Partial<PolicyPreviewResponse> = {}): PolicyPreviewResponse {
  return {
    candidates: [],
    count: 3,
    pool: 12,
    counts: { eligible: 3, score_below_min: 8, hidden: 1 },
    budget_applied: false,
    ...over,
  };
}
