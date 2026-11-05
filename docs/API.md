# SteamSelfGifter API Documentation

This document defines the API contract between the backend and frontend services.

**Base URL:** `/api/v1`

**Response Format:** All responses follow this structure:
```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "timestamp": "2026-01-12T18:00:00.000000Z"
  }
}
```

**Error Format:**
```json
{
  "detail": "Error message"
}
```
or
```json
{
  "error": {
    "message": "Error message",
    "code": "ERR_CODE",
    "details": { ... }
  }
}
```

---

## Settings

### GET /settings/
Get current application settings.

**Response:**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "phpsessid": "string | null",
    "user_agent": "string",
    "xsrf_token": "string | null",
    "safety_check_enabled": true,
    "auto_hide_unsafe": true,
    "autojoin_enabled": false,
    "autojoin_start_at": 350,
    "autojoin_stop_at": 200,
    "autojoin_min_price": 10,
    "autojoin_min_score": 7,
    "autojoin_min_reviews": 1000,
    "autojoin_max_game_age": null,
    "autojoin_priorities": [{"type": "wishlist"}],
    "excluded_genres": [],
    "included_genres": [],
    "scan_interval_minutes": 30,
    "max_entries_per_cycle": 10,
    "automation_enabled": false,
    "max_scan_pages": 3,
    "entry_delay_min": 8,
    "entry_delay_max": 12,
    "log_retention_days": 30,
    "last_synced_at": "datetime | null",
    "created_at": "datetime",
    "updated_at": "datetime"
  }
}
```

### PUT /settings/
Update application settings (partial updates supported).

**Request Body:** (all fields optional)
```json
{
  "phpsessid": "string",
  "user_agent": "string",
  "safety_check_enabled": true,
  "auto_hide_unsafe": true,
  "autojoin_enabled": true,
  "autojoin_start_at": 350,
  "autojoin_stop_at": 200,
  "autojoin_min_price": 10,
  "autojoin_min_score": 7,
  "autojoin_min_reviews": 1000,
  "autojoin_max_game_age": 5,
  "autojoin_priorities": [{"type": "dlc"}, {"type": "ending_soon", "threshold_minutes": 60}, {"type": "wishlist"}],
  "excluded_genres": ["Sports", "Racing"],
  "included_genres": ["RPG", "Indie"],
  "scan_interval_minutes": 30,
  "max_entries_per_cycle": 10,
  "automation_enabled": true,
  "max_scan_pages": 3,
  "entry_delay_min": 8,
  "entry_delay_max": 12,
  "log_retention_days": 30
}
```

**Null and omitted fields.** An omitted field is unchanged. An explicit `null` is stored as `NULL` for `phpsessid`, `xsrf_token`, `autojoin_min_score`, `autojoin_min_reviews` and `autojoin_max_game_age` (the filter is off). Explicit `null` for `autojoin_priorities` leaves it unchanged. Explicit `null` for any other field returns 400 `"<field> cannot be null"` and writes nothing. A body that reduces to nothing (`{}`) returns 400 `"No fields provided for update"`. The removed keys `wishlist_priority_enabled`, `dlc_priority_enabled`, `ending_soon_priority_enabled` and `ending_soon_threshold_minutes` are ignored if sent.

| Field | Type | Default / reset | Validation (422 on failure, nothing written) |
|---|---|---|---|
| `autojoin_priorities` | ordered list of 0 to 3 items | `[{"type": "wishlist"}]` | item is `{"type": "wishlist"}`, `{"type": "dlc"}` or `{"type": "ending_soon", "threshold_minutes": 5..10080}`; no duplicate types, no extra keys |
| `autojoin_min_score` | int 0..10 or `null` | 7 | `null` = no minimum; `0` still requires cached game data |
| `autojoin_min_reviews` | int >= 0 or `null` | 1000 | same semantics as the score |
| `max_entries_per_cycle` | int >= 1 | 10 | never `null` |
| `excluded_genres`, `included_genres` | list of Steam genre names | `[]` | see below |

`excluded_genres` and `included_genres` are lists of Steam genre names (never `null` in responses). `[]` clears a list. The server normalizes each in this order: strip each item, drop empty items, reject any item longer than 64 characters (422), dedupe case-insensitively (ASCII) keeping the first spelling, reject more than 50 items (422). A non-list value or non-string items return 422, and the message names the field. The response echoes the normalized list in the user's order, e.g. `[" Action", "action", "Indie", ""]` is stored as `["Action", "Indie"]`. `POST /settings/reset` sets both back to `[]`. The two lists may overlap; exclusion wins at evaluation time.

**Auto-join decision.** One engine, `services/eligibility.py`, decides every giveaway: it runs in the automation cycle, in the preview endpoints, in the Giveaways lens and when labelling a giveaway. The stages, in order:

1. Gates, never lifted: `expired`, `hidden`, `entered`, `unsafe`.
2. Priority match against `autojoin_priorities`: the first matching item gives the giveaway its `priority` and `rank`.
3. Exemption: `wishlist` and `dlc` items skip the filters for a giveaway that matches any such item (`lifted_by`); `ending_soon` never skips them.
4. Filters, first failure wins: `price_below_min`, `genre_excluded`, `genre_not_included`, `no_game_data`, `score_below_min`, `reviews_below_min`, `game_too_old`.
5. Ordering, then the cycle budget (`budget_floor`, `cycle_cap`, `points_accumulating`).

Unknown data: a giveaway with no cached game, or genres `null` or `[]`, is never excluded by `excluded_genres`. With a non-empty `included_genres`, unknown or empty genres fail (`genre_not_included`). A score, reviews or age threshold that is set requires cached game data (`no_game_data` otherwise); an unknown score or review count counts as 0, and an unknown release date fails the age limit. Games cached before genres were stored get them from the background stale-game refresh over the next cycles. Only Steam store genres are matched.

**Response:** Same as GET /settings/

**Entry order:** each automation cycle enters candidates by priority rank (the order of `autojoin_priorities`), first item first. Inside an `ending_soon` group the soonest `end_time` comes first (a giveaway is ending soon when `end_time - now` is at most `threshold_minutes`, inclusive); everything else, including the unmatched rest, stays in price-descending order. A giveaway that also matches a later exempt item sorts before one that does not. `max_entries_per_cycle` and the `autojoin_stop_at` budget apply after the ordering, on the points balance actually spent; giveaways skipped for points do not use a cap slot. With `autojoin_priorities` empty, wishlist and DLC giveaways obey every filter and the order is price descending.

### POST /settings/test-session
Test if the configured PHPSESSID is valid.

**Response (success):**
```json
{
  "success": true,
  "data": {
    "valid": true,
    "username": "kernelcoffee",
    "points": 485
  }
}
```

**Response (invalid session):**
```json
{
  "success": true,
  "data": {
    "valid": false,
    "error": "Could not extract XSRF token - not authenticated?"
  }
}
```

### POST /settings/validate
Validate current configuration.

**Response:**
```json
{
  "success": true,
  "data": {
    "is_valid": true,
    "errors": [],
    "warnings": []
  }
}
```

---

## Giveaways

### GET /giveaways/
List giveaways with optional filters.

**Query Parameters:**
- `status`: `active` | `entered` | `all` (default: active)
- `is_entered`: `true` | `false`
- `is_hidden`: `true` | `false`
- `type`: `game` | `dlc` | `bundle`
- `search`: string (search in game_name)
- `sort`: `end_time` | `price` | `discovered_at`
- `order`: `asc` | `desc`
- `limit`: number (1-100, default: 50)
- `offset`: number (default: 0)

**Response:**
```json
{
  "success": true,
  "data": {
    "giveaways": [
      {
        "id": 1,
        "code": "FDVzQ",
        "url": "https://www.steamgifts.com/giveaway/FDVzQ/",
        "game_id": 123,
        "game_name": "Portal 2",
        "price": 15,
        "copies": 1,
        "end_time": "2026-01-15T12:00:00",
        "is_hidden": false,
        "is_entered": false,
        "is_safe": true,
        "safety_score": 85,
        "discovered_at": "2026-01-12T10:00:00",
        "entered_at": null,
        "created_at": "2026-01-12T10:00:00",
        "updated_at": "2026-01-12T10:00:00"
      }
    ],
    "count": 155
  }
}
```

Giveaway objects returned by the list endpoints (`/giveaways/`, `/giveaways/active`, `/giveaways/wishlist`, `/giveaways/dlc`, `/giveaways/entered`, `/giveaways/won`) and by `GET /giveaways/{code}` also carry fields joined from the cached game, among them `game_thumbnail` and `game_genres`. `game_genres` is the cached game's Steam genre list (possibly `[]`), or `null` when the giveaway has no `game_id`, the game is not cached, or its genres were not fetched yet. `eligibility_*` fields are described above.

Every giveaway object also carries the stored result of the last automation cycle:

| Field | Type | Meaning |
|---|---|---|
| `eligibility_reason` | string or null | decision code, e.g. `eligible`, `price_below_min`, `genre_not_included`, `budget_floor`; null until evaluated |
| `eligibility_detail` | object or null | small flat object with the user's values (actual versus threshold) |
| `eligibility_label` | string or null | `eligibility_reason` rendered server-side in the user's terms; `Joinable` for an enter outcome |
| `eligibility_kind` | `enter` \| `gate` \| `filter` \| `budget` or null | code family (not a database column) |
| `eligibility_checked_at` | datetime (Z) or null | when the cycle recorded it |

`price_above_max` is no longer produced. Stored `price_above_max` reasons were cleared by the migration.

### GET /giveaways/registry
The decision engine as data: `gates`, `filters` (each with the `setting` that drives it), `outcomes`, `priority_types` (label, description, `exempt_from_filters`, `params` with min, max and default) and `limits` (`genre_max_items` 50, `genre_max_length` 64, `max_priority_items` 3). The frontend fetches it once and holds no copy of labels or bounds. It contains no session data and is declared before `/{code}`.

### POST /giveaways/preview
Dry-run a policy without saving it. Query: `limit` (1-100, default 20). Body: exactly the seven policy fields, all required, validated like `PUT /settings/`: `autojoin_min_price`, `autojoin_min_score`, `autojoin_min_reviews`, `autojoin_max_game_age`, `excluded_genres`, `included_genres`, `autojoin_priorities`. A missing or invalid field returns 422; unknown extra keys are ignored.

```json
{
  "success": true,
  "data": {
    "candidates": [
      {
        "code": "FDVzQ",
        "decision": {
          "code": "eligible", "label": "Joinable",
          "detail": {"priority": "wishlist", "rank": 0, "lifted_by": "wishlist"},
          "priority": "wishlist", "rank": 0, "lifted_by": "wishlist"
        }
      }
    ],
    "count": 3,
    "pool": 120,
    "counts": {"eligible": 3, "score_below_min": 80, "hidden": 37},
    "budget_applied": false
  }
}
```

`candidates` holds full giveaway objects (shortened above) plus `decision`, in entry order, sliced to `limit`. `count` is the total number of enter candidates; `pool` is the number of active, not-entered giveaways evaluated (hidden included); `counts` maps each code to its number and sums to `pool`. Nothing is persisted, no points are fetched, no budget is applied, and nothing is sent to SteamGifts or Steam. The stored `autojoin_priorities` is not read, so a corrupt stored list does not affect this call.

### GET /giveaways/eligible
Same response as `POST /giveaways/preview`, computed from the saved settings. Query: `limit` (1-100, default 20); no other parameters. The key `giveaways` is no longer returned. A stored priority list that cannot be parsed returns the 500 envelope with code `CONFIG_002`. Stored `eligibility_*` fields are not changed.

### Auto-join lens
`GET /giveaways/active`, `/giveaways/wishlist` and `/giveaways/dlc` accept `lens=autojoin` (any other value returns 422). The pool is the tab's not-entered rows under the usual conditions and browse parameters (`min_score`, `is_safe`, `min_chance`, `ending_within` where accepted), unpaginated; the saved policy is evaluated live. Response data: `{"giveaways": [...candidates with decision, in entry order, sliced by limit/offset], "count": <enter candidates in the pool>, "lens": "autojoin", "budget_applied": false}`. Without `lens` the response is unchanged. `GET /giveaways/?is_entered=false` applies no policy and no longer accepts `min_price`, `max_price`, `min_score` or `min_reviews`.

### GET /giveaways/{code}
Get a single giveaway by code.

**Path Parameters:**
- `code`: string (SteamGifts giveaway code, e.g., "FDVzQ")

**Response:**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "code": "FDVzQ",
    "url": "https://www.steamgifts.com/giveaway/FDVzQ/",
    "game_id": 123,
    "game_name": "Portal 2",
    "price": 15,
    "copies": 1,
    "end_time": "2026-01-15T12:00:00",
    "is_hidden": false,
    "is_entered": false,
    "is_safe": true,
    "safety_score": 85,
    "discovered_at": "2026-01-12T10:00:00",
    "entered_at": null,
    "created_at": "2026-01-12T10:00:00",
    "updated_at": "2026-01-12T10:00:00"
  }
}
```

### POST /giveaways/{code}/enter
Enter a giveaway.

**Path Parameters:**
- `code`: string (SteamGifts giveaway code)

**Request Body:** (optional)
```json
{
  "entry_type": "manual"
}
```
- `entry_type`: `manual` | `auto` | `wishlist` (default: manual)

**Response (success):**
```json
{
  "success": true,
  "data": {
    "success": true,
    "points_spent": 15,
    "message": "Successfully entered giveaway",
    "entry_id": 42
  }
}
```

**Response (failure - 400):**
```json
{
  "detail": "Already entered" | "Insufficient points" | "Giveaway ended"
}
```

### POST /giveaways/{code}/hide
Hide a giveaway from recommendations.

**Path Parameters:**
- `code`: string (SteamGifts giveaway code)

**Response:**
```json
{
  "success": true,
  "data": {
    "message": "Giveaway hidden",
    "code": "FDVzQ"
  }
}
```

### POST /giveaways/{code}/unhide
Unhide a giveaway.

**Path Parameters:**
- `code`: string (SteamGifts giveaway code)

**Response:**
```json
{
  "success": true,
  "data": {
    "message": "Giveaway unhidden",
    "code": "FDVzQ"
  }
}
```

**Status:** NOT IMPLEMENTED - needs to be added to backend

### POST /giveaways/sync
Trigger a manual sync of giveaways from SteamGifts.

**Query Parameters:**
- `pages`: number (1-10, default: 3)

**Response:**
```json
{
  "success": true,
  "data": {
    "new": 50,
    "updated": 10,
    "pages_synced": 3
  }
}
```

---

## Games

Cached Steam store data. Every game object (`GET /games/`, `/games/{app_id}`, `/games/search/{query}`, `/games/highly-rated`) carries `"genres": string[] | null` and `"categories": string[] | null`: the Steam `appdetails` genre and category descriptions in Steam's order (e.g. `["Action", "Indie"]`, `["Single-player", "Steam Achievements"]`), `[]` when Steam returned none, `null` when the row was cached before genres were stored and has not been refreshed yet. Store data is fetched with `l=english`, so the names are English.

### GET /games/genres
Distinct genres across all cached games (any type), with the number of games carrying each. Sorted by `count` descending, then `name` ascending. Games with `genres` `null` or `[]` contribute nothing; an empty cache returns `{"genres": []}`. No query parameters, no pagination.

**Response:**
```json
{
  "success": true,
  "data": {
    "genres": [
      { "name": "Action", "count": 2 },
      { "name": "Indie", "count": 1 },
      { "name": "RPG", "count": 1 }
    ]
  }
}
```

### GET /games/{app_id}
Get a game by Steam App ID, fetching it from Steam when it is not cached (or when `force_refresh=true`).

**Query Parameters:**
- `force_refresh`: `true` | `false` (default: false)

**Errors:**
- 404 `"Game with App ID {app_id} not found"` when Steam does not serve the app.
- 429 when the app is not cached and Steam is rate limiting (see Steam cool-down below). A cached row is still returned with 200 during the cool-down.
```json
{
  "error": {
    "code": "STEAM_003",
    "message": "Steam is rate limiting requests, retry in 120 s",
    "details": { "app_id": 620, "retry_after_seconds": 120 }
  }
}
```

### POST /games/{app_id}/refresh
Force a refresh of one game from Steam.

**Response:**
```json
{
  "success": true,
  "data": {
    "refreshed": true,
    "message": "Game data refreshed successfully",
    "last_refreshed_at": "2026-01-12T10:00:00Z",
    "retry_after_seconds": null
  }
}
```

When the refresh does not complete, `refreshed` is `false`, `last_refreshed_at` is `null` and the cached row is kept:
- rate limited (including when `appdetails` was saved but `GetAppReviews` was throttled): `"Steam is rate limiting requests, retry in N s"`, with `retry_after_seconds` set
- unavailable on Steam: `"Game with App ID N not found on Steam"`
- any other Steam failure: `"Steam request failed, cached data kept"`; this includes the case where `appdetails` was saved (name, genres, release date updated) but `GetAppReviews` failed on a row with no cached reviews: the row then keeps its zeros, is not marked refreshed, and is retried by the stale refresh after 6 h

**Steam cool-down:** any Steam 429 (from `appdetails` or `GetAppReviews`), or an `appdetails` reply whose body is not an object (e.g. HTTP 200 with `null`), starts a process-wide 180 s cool-down during which no Steam request is sent. Cached rows are served as is, uncached apps get no row, and `POST /games/refresh-stale` refreshes nothing.

---

## Entries

### GET /entries/
List entry history.

**Query Parameters:**
- `status`: `success` | `failed` | `all`
- `type`: `manual` | `auto` | `wishlist`
- `limit`: number (1-100, default: 50)
- `offset`: number (default: 0)

**Response:**
```json
{
  "success": true,
  "data": {
    "entries": [
      {
        "id": 1,
        "giveaway_id": 42,
        "points_spent": 15,
        "status": "success",
        "entry_type": "manual",
        "error_message": null,
        "entered_at": "2026-01-12T15:30:00",
        "created_at": "2026-01-12T15:30:00",
        "giveaway": {
          "code": "FDVzQ",
          "game_name": "Portal 2",
          "price": 15
        }
      }
    ],
    "count": 42
  }
}
```

---

## Analytics

### GET /analytics/overview
Get comprehensive analytics overview.

**Response:**
```json
{
  "success": true,
  "data": {
    "giveaways": {
      "total": 155,
      "active": 100,
      "entered": 30,
      "hidden": 5
    },
    "entries": {
      "total": 42,
      "successful": 40,
      "failed": 2,
      "success_rate": 95.2,
      "total_points_spent": 450
    },
    "by_type": {
      "manual": 10,
      "auto": 30,
      "wishlist": 2
    }
  }
}
```

### GET /analytics/entries/summary
Get entry statistics summary.

**Response:**
```json
{
  "success": true,
  "data": {
    "total_entries": 42,
    "successful_entries": 40,
    "failed_entries": 2,
    "success_rate": 95.2,
    "total_points_spent": 450,
    "average_points_per_entry": 10.7,
    "by_type": {
      "manual": 10,
      "auto": 30,
      "wishlist": 2
    }
  }
}
```

### GET /analytics/giveaways/summary
Get giveaway statistics summary.

**Response:**
```json
{
  "success": true,
  "data": {
    "total_giveaways": 155,
    "active_giveaways": 100,
    "entered_giveaways": 30,
    "hidden_giveaways": 5,
    "expiring_24h": 25
  }
}
```

### GET /analytics/games/summary
Get game cache statistics.

**Response:**
```json
{
  "success": true,
  "data": {
    "total_games": 135,
    "games": 120,
    "dlc": 10,
    "bundles": 5,
    "stale_games": 3
  }
}
```

### GET /analytics/dashboard
Get all dashboard data in a single request.

**Response:**
```json
{
  "success": true,
  "data": {
    "giveaways": {
      "total": 155,
      "active": 100,
      "entered": 30
    },
    "entries": {
      "total": 42,
      "successful": 40,
      "success_rate": 95.2,
      "total_points_spent": 450
    },
    "expiring_soon": [
      {
        "code": "FDVzQ",
        "game_name": "Portal 2",
        "price": 15,
        "end_time": "2026-01-12T18:00:00"
      }
    ],
    "recent_entries": [
      {
        "id": 1,
        "giveaway_id": 42,
        "points_spent": 15,
        "status": "success",
        "entered_at": "2026-01-12T15:30:00"
      }
    ]
  }
}
```

---

## Scheduler

### GET /scheduler/status
Get scheduler status.

**Response:**
```json
{
  "success": true,
  "data": {
    "running": false,
    "paused": false,
    "job_count": 2,
    "jobs": []
  }
}
```

### POST /scheduler/start
Start the scheduler.

**Response:**
```json
{
  "success": true,
  "data": {
    "message": "Scheduler started",
    "running": true
  }
}
```

### POST /scheduler/stop
Stop the scheduler.

**Response:**
```json
{
  "success": true,
  "data": {
    "message": "Scheduler stopped",
    "running": false
  }
}
```

### POST /scheduler/scan
Trigger a manual giveaway scan.

**Response:**
```json
{
  "success": true,
  "data": {
    "new": 50,
    "updated": 10,
    "pages_scanned": 3,
    "scan_time": 15.5,
    "skipped": false
  }
}
```

### POST /scheduler/scan/quick
Trigger a quick scan (single page).

**Response:** Same as POST /scheduler/scan

### POST /scheduler/enter/{giveaway_code}
Manually enter a specific giveaway.

**Path Parameters:**
- `giveaway_code`: string (SteamGifts giveaway code)

**Response (success):**
```json
{
  "success": true,
  "data": {
    "success": true,
    "giveaway_code": "FDVzQ",
    "points_spent": 15
  }
}
```

---

## System

### GET /system/health
Health check endpoint.

**Response:**
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "timestamp": "2026-01-12T18:00:00.000000",
    "version": "2.0.0"
  }
}
```

---

## Logs

### GET /logs/
Get activity logs.

**Query Parameters:**
- `level`: `info` | `warning` | `error`
- `type`: `scan` | `entry` | `auth` | `system`
- `limit`: number (1-100, default: 50)
- `offset`: number (default: 0)

**Response:**
```json
{
  "success": true,
  "data": {
    "logs": [
      {
        "id": 1,
        "level": "info",
        "type": "scan",
        "message": "Scan completed",
        "details": { "new": 50, "updated": 10 },
        "created_at": "2026-01-12T15:00:00"
      }
    ],
    "count": 100
  }
}
```

**Status:** Check if implemented in backend

---

## WebSocket

### WS /ws
WebSocket connection for real-time updates.

**Events (server -> client):**
```json
{
  "type": "scan_completed",
  "data": {
    "new": 50,
    "updated": 10
  }
}
```

```json
{
  "type": "entry_created",
  "data": {
    "giveaway_code": "FDVzQ",
    "game_name": "Portal 2",
    "points_spent": 15
  }
}
```

```json
{
  "type": "points_updated",
  "data": {
    "points": 470,
    "previous": 485
  }
}
```

---

## Missing Endpoints (to be implemented)

The following endpoints are expected by the frontend but not yet implemented:

1. **POST /giveaways/{code}/unhide** - Unhide a giveaway
2. **GET /logs/** - Activity logs endpoint
3. **DELETE /logs/** - Clear logs
4. **GET /analytics/entries/trends** - Entry trends over time

---

## Type Definitions

### Giveaway
```typescript
interface Giveaway {
  id: number;
  code: string;              // SteamGifts giveaway code (e.g., "FDVzQ")
  url: string;
  game_id: number | null;
  game_name: string;
  price: number;             // Points cost
  copies: number;
  end_time: string | null;   // ISO datetime
  is_hidden: boolean;
  is_entered: boolean;
  is_safe: boolean;
  safety_score: number | null;
  game_genres?: string[] | null; // joined from the cached game; null = unknown
  discovered_at: string;
  entered_at: string | null;
  created_at: string;
  updated_at: string;
}
```

### Entry
```typescript
interface Entry {
  id: number;
  giveaway_id: number;
  points_spent: number;
  status: 'success' | 'failed';
  entry_type: 'manual' | 'auto' | 'wishlist';
  error_message: string | null;
  entered_at: string;
  created_at: string;
}
```

### Settings
```typescript
type AutojoinPriorityItem =
  | { type: "wishlist" }
  | { type: "dlc" }
  | { type: "ending_soon"; threshold_minutes: number };

interface Settings {
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
  autojoin_min_score: number | null;
  autojoin_min_reviews: number | null;
  autojoin_max_game_age: number | null;
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
```

### GenreList
```typescript
interface GenreCount {
  name: string;
  count: number;
}

interface GenreList {
  genres: GenreCount[];  // GET /games/genres
}
```
