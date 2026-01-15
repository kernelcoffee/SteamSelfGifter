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
    "dlc_enabled": false,
    "autojoin_enabled": false,
    "autojoin_start_at": 350,
    "autojoin_stop_at": 200,
    "autojoin_min_price": 10,
    "autojoin_min_score": 7,
    "autojoin_min_reviews": 1000,
    "scan_interval_minutes": 30,
    "max_entries_per_cycle": null,
    "automation_enabled": false,
    "max_scan_pages": 3,
    "entry_delay_min": 8,
    "entry_delay_max": 12,
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
  "dlc_enabled": true,
  "autojoin_enabled": true,
  "autojoin_start_at": 350,
  "autojoin_stop_at": 200,
  "autojoin_min_price": 10,
  "autojoin_min_score": 7,
  "autojoin_min_reviews": 1000,
  "scan_interval_minutes": 30,
  "max_entries_per_cycle": 10,
  "automation_enabled": true,
  "max_scan_pages": 3,
  "entry_delay_min": 8,
  "entry_delay_max": 12
}
```

**Response:** Same as GET /settings/

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
interface Settings {
  id: number;
  phpsessid: string | null;
  user_agent: string;
  xsrf_token: string | null;
  dlc_enabled: boolean;
  autojoin_enabled: boolean;
  autojoin_start_at: number;
  autojoin_stop_at: number;
  autojoin_min_price: number;
  autojoin_min_score: number;
  autojoin_min_reviews: number;
  scan_interval_minutes: number;
  max_entries_per_cycle: number | null;
  automation_enabled: boolean;
  max_scan_pages: number;
  entry_delay_min: number;
  entry_delay_max: number;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
}
```
