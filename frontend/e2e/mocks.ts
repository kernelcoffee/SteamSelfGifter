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
  dlc_enabled: false,
  safety_check_enabled: true,
  auto_hide_unsafe: true,
  autojoin_enabled: true,
  autojoin_start_at: 300,
  autojoin_stop_at: 50,
  autojoin_min_price: 10,
  autojoin_min_score: 7,
  autojoin_min_reviews: 1000,
  autojoin_max_game_age: null,
  wishlist_priority_enabled: true,
  scan_interval_minutes: 30,
  max_entries_per_cycle: 10,
  automation_enabled: true,
  max_scan_pages: 3,
  entry_delay_min: 5,
  entry_delay_max: 15,
  last_synced_at: null,
  created_at: '2026-01-01T00:00:00',
  updated_at: '2026-01-01T00:00:00',
};

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
    end_time: inHours(24 + id),
    discovered_at: inHours(-2),
    entered_at: null,
    is_hidden: false,
    is_entered: false,
    is_wishlist: false,
    is_won: false,
    won_at: null,
    is_safe: true,
    safety_score: 95,
    created_at: inHours(-2),
    updated_at: inHours(-2),
    game_thumbnail: null,
    game_review_score: 9,
    game_total_reviews: 12000,
    game_review_summary: 'Very Positive',
    eligibility_reason: null,
    eligibility_checked_at: null,
    ...over,
  };
}

export const mockGiveaways = [
  giveaway(1, { game_name: 'Portal Reloaded' }),
  giveaway(2, { game_name: 'Half-Life 3', is_wishlist: true }),
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
      return route.fulfill(ok({ period: 'week', trends: [] }));
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
