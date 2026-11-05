import type { Page, Route } from '@playwright/test';

/** Envelope every backend response uses. */
function ok(data: unknown) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ success: true, data }),
  };
}

const NOW = Date.now();
const inHours = (h: number) => new Date(NOW + h * 3_600_000).toISOString();

export const mockSettings = {
  id: 1,
  phpsessid: 'e2e-session-cookie',
  user_agent: 'SteamSelfGifter/2.0',
  xsrf_token: null,
  safety_check_enabled: true,
  auto_hide_unsafe: true,
  autojoin_enabled: true,
  autojoin_start_at: 300,
  autojoin_stop_at: 50,
  autojoin_min_price: 10,
  autojoin_min_score: 7,
  autojoin_min_reviews: 1000,
  autojoin_max_game_age: null,
  autojoin_priorities: [{ type: 'wishlist' }] as Array<Record<string, unknown>>,
  excluded_genres: [] as string[],
  included_genres: [] as string[],
  scan_interval_minutes: 30,
  max_entries_per_cycle: 10,
  automation_enabled: true,
  max_scan_pages: 3,
  entry_delay_min: 5,
  entry_delay_max: 15,
  log_retention_days: 30,
  last_synced_at: null,
  created_at: '2026-01-01T00:00:00',
  updated_at: '2026-01-01T00:00:00',
};

/** GET /api/v1/giveaways/registry, exactly as the contract defines it. */
export const mockRegistry = {
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

/** Live decision the mocked engine gives every candidate. */
export const mockDecision = {
  code: 'eligible',
  label: 'Joinable',
  detail: { priority: 'wishlist', rank: 0, lifted_by: 'wishlist' },
  priority: 'wishlist',
  rank: 0,
  lifted_by: 'wishlist',
};

/** Mocked dry run: the count follows the body so specs can see what was sent. */
function previewCount(body: { autojoin_min_score?: number | null; included_genres?: string[] }) {
  if (body.autojoin_min_score !== null && body.autojoin_min_score !== undefined && body.autojoin_min_score <= 5) {
    return 5;
  }
  return (body.included_genres ?? []).length > 0 ? 1 : 3;
}

export const mockDashboard = {
  session: { configured: true, valid: true, username: 'e2e-user', error: null },
  points: { current: 342 },
  entries: { total: 120, today: 4, entered_30d: 60, wins_30d: 3, win_rate: 5.0 },
  giveaways: { active: 57, entered: 12, wins: 9 },
  safety: { checked: 40, safe: 38, unsafe: 2, unchecked: 17 },
  scheduler: { running: true, paused: false, last_scan: inHours(-1), next_scan: inHours(1) },
};

export const mockSchedulerStatus = {
  running: true,
  paused: false,
  job_count: 1,
  jobs: [
    { id: 'automation_cycle', name: 'scan_giveaways', next_run: inHours(1), pending: false },
  ],
};

function giveaway(id: number, over: Record<string, unknown> = {}) {
  return {
    id,
    code: `Code${id}`,
    url: `https://www.steamgifts.com/giveaway/Code${id}/`,
    game_name: `Test Game ${id}`,
    game_id: 400 + id,
    price: 25 + id,
    copies: 1,
    entries: 100,
    win_chance: 1.0,
    end_time: inHours(24 + id),
    discovered_at: inHours(-2),
    entered_at: null,
    is_hidden: false,
    is_entered: false,
    is_wishlist: false,
    is_dlc: false,
    is_won: false,
    won_at: null,
    is_safe: true,
    safety_score: 95,
    created_at: inHours(-2),
    updated_at: inHours(-2),
    game_thumbnail: null,
    game_genres: ['Action', 'Indie'],
    game_review_score: 9,
    game_total_reviews: 12000,
    game_review_summary: 'Very Positive',
    eligibility_reason: null,
    eligibility_detail: null,
    eligibility_checked_at: null,
    eligibility_label: null,
    eligibility_kind: null,
    ...over,
  };
}

export const mockGiveaways = [
  giveaway(1, {
    game_name: 'Portal Reloaded',
    eligibility_reason: 'score_below_min',
    eligibility_detail: { score: 6, min_score: 7 },
    eligibility_label: 'Review score 6 is below your minimum 7',
    eligibility_kind: 'filter',
    eligibility_checked_at: inHours(-0.2),
  }),
  giveaway(2, { game_name: 'Half-Life 3', is_wishlist: true, game_genres: null }),
  giveaway(3, { game_name: 'Stardew Galaxy', is_entered: true, entered_at: inHours(-1) }),
];

export interface ApiCall {
  method: string;
  url: string;
  postData: string | null;
}

/**
 * Install route mocks for every /api/v1 endpoint the app touches and swallow
 * the WebSocket connection. Returns a log of API calls for assertions.
 */
export async function mockApi(page: Page): Promise<ApiCall[]> {
  const calls: ApiCall[] = [];

  // The app connects to /ws/events on load; accept and stay silent.
  await page.routeWebSocket('**/ws/events', () => {
    /* no server messages */
  });

  await page.route('**/api/v1/**', async (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;
    const method = req.method();
    calls.push({ method, url: path + url.search, postData: req.postData() });

    // --- Settings ---
    if (path === '/api/v1/settings' && method === 'GET') {
      return route.fulfill(ok(mockSettings));
    }
    if (path === '/api/v1/settings' && method === 'PUT') {
      const body = JSON.parse(req.postData() ?? '{}');
      return route.fulfill(
        ok({ ...mockSettings, ...body, updated_at: new Date(NOW).toISOString() })
      );
    }
    if (path === '/api/v1/settings/test-session') {
      return route.fulfill(ok({ valid: true, username: 'e2e-user', points: 342, error: null }));
    }

    // --- Analytics / dashboard ---
    if (path === '/api/v1/analytics/dashboard') {
      return route.fulfill(ok(mockDashboard));
    }

    // --- Scheduler ---
    if (path === '/api/v1/scheduler/status') {
      return route.fulfill(ok(mockSchedulerStatus));
    }
    if (path === '/api/v1/scheduler/stop') {
      return route.fulfill(ok({ ...mockSchedulerStatus, running: false, jobs: [] }));
    }
    if (path === '/api/v1/scheduler/start') {
      return route.fulfill(ok(mockSchedulerStatus));
    }

    // --- Auto-join engine (before the generic giveaways matcher) ---
    if (path === '/api/v1/giveaways/registry') {
      return route.fulfill(ok(mockRegistry));
    }
    if (path === '/api/v1/giveaways/preview' && method === 'POST') {
      const count = previewCount(JSON.parse(req.postData() ?? '{}'));
      return route.fulfill(
        ok({
          candidates: [],
          count,
          pool: 12,
          counts: { eligible: count, score_below_min: 11 - count, hidden: 1 },
          budget_applied: false,
        })
      );
    }
    if (path === '/api/v1/giveaways/eligible') {
      const candidates = mockGiveaways
        .filter((g) => !g.is_entered)
        .map((g) => ({ ...g, decision: mockDecision }));
      return route.fulfill(
        ok({
          candidates,
          count: candidates.length,
          pool: mockGiveaways.length,
          counts: { eligible: candidates.length, entered: 1 },
          budget_applied: false,
        })
      );
    }
    if (path.startsWith('/api/v1/giveaways') && url.searchParams.get('lens') === 'autojoin') {
      const candidates = mockGiveaways
        .filter((g) => !g.is_entered)
        .map((g) => ({ ...g, decision: mockDecision }));
      return route.fulfill(
        ok({ giveaways: candidates, count: candidates.length, lens: 'autojoin', budget_applied: false })
      );
    }

    // --- Giveaways ---
    if (/^\/api\/v1\/giveaways\/[^/]+\/enter$/.test(path)) {
      return route.fulfill(ok({ success: true, points_spent: 26, error: null }));
    }
    if (path.startsWith('/api/v1/giveaways')) {
      const search = url.searchParams.get('search')?.toLowerCase();
      const filtered = search
        ? mockGiveaways.filter((g) => g.game_name.toLowerCase().includes(search))
        : mockGiveaways;
      return route.fulfill(ok({ giveaways: filtered, count: filtered.length }));
    }

    // --- Entries (History page maps {entries, count} -> {items, total}) ---
    if (path.startsWith('/api/v1/entries')) {
      return route.fulfill(ok({ entries: [], count: 0 }));
    }

    // --- Analytics summaries (Analytics page) ---
    if (path === '/api/v1/analytics/entries/summary') {
      return route.fulfill(
        ok({
          total: 120,
          successful: 117,
          failed: 3,
          total_points_spent: 2900,
          success_rate: 97.5,
          by_type: { auto: 100, manual: 15, wishlist: 5 },
        })
      );
    }
    if (path === '/api/v1/analytics/giveaways/summary') {
      return route.fulfill(
        ok({ total: 300, active: 57, entered: 12, hidden: 4, wins: 9, win_rate: 5.0 })
      );
    }
    if (path === '/api/v1/analytics/games/summary') {
      return route.fulfill(ok({ total: 200, games: 180, dlc: 15, bundles: 5, stale_count: 3 }));
    }
    if (path.startsWith('/api/v1/analytics/entries/trends')) {
      const trends = Array.from({ length: 30 }, (_, i) => {
        const d = new Date(Date.now() - (29 - i) * 86_400_000);
        const successful = (i * 7) % 11;
        const failed = i % 3 === 0 ? 1 : 0;
        return {
          date: d.toISOString().slice(0, 10),
          entries: successful + failed,
          successful,
          failed,
          points_spent: successful * 27,
          wins: i % 9 === 0 ? 1 : 0,
        };
      });
      return route.fulfill(ok({ period: 'month', trends }));
    }

    // --- Games ---
    if (path === '/api/v1/games/genres') {
      return route.fulfill(
        ok({
          genres: [
            { name: 'Action', count: 12 },
            { name: 'Indie', count: 9 },
            { name: 'Massively Multiplayer', count: 3 },
          ],
        })
      );
    }

    // --- System logs (Dashboard activity feed / Logs page) ---
    if (path.startsWith('/api/v1/system/logs')) {
      return route.fulfill(ok({ logs: [], count: 0 }));
    }

    // --- Fallback: empty success so unmodelled endpoints don't hang ---
    return route.fulfill(ok({}));
  });

  return calls;
}
