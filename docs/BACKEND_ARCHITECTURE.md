# Backend Architecture & Workflow

> Status: as-built description of `backend/src` (~16k LoC). The automation-layer
> redundancy called out in earlier revisions (§6) has now been consolidated —
> see §6 for the before/after and §7 for the resulting shape.
> Audience: maintainers. Last reviewed: 2026-06-17.

---

## 1. What the backend does

SteamSelfGifter is a single-user bot that logs into SteamGifts.com with a
session cookie (`PHPSESSID`), scrapes the giveaway listings, enriches each game
with data from the Steam store API, and automatically enters giveaways that
match the user's criteria — on a schedule, unattended. It also tracks wins,
detects unsafe ("trap") giveaways, and exposes everything over a REST + WebSocket
API consumed by the React frontend.

There is **no external concurrency model and no auth** by design: it runs as one
process on localhost (or in a single container), one user, one SQLite database.

---

## 2. Layered architecture

The code is a clean, conventional layered stack. Dependencies point downward
only.

```
            ┌─────────────────────────────────────────────┐
  HTTP/WS   │  api/         routers, schemas, deps, main    │
            ├─────────────────────────────────────────────┤
  logic     │  services/    giveaway, game, settings,       │
            │               notification, scheduler         │
            ├──────────────────────┬──────────────────────┤
  data      │  repositories/       │  utils/  (external)    │
            │  (SQLAlchemy)        │  steamgifts_client     │
            │                      │  steam_client          │
            ├──────────────────────┴──────────────────────┤
  models    │  models/      ORM entities                    │
            ├─────────────────────────────────────────────┤
  infra     │  core/ (config, events, logging, exceptions)  │
            │  db/   (session, migrations)                  │
            └─────────────────────────────────────────────┘

  workers/  ── background jobs that drive services on a schedule
              (APScheduler). Sit "beside" the API, share the services.
```

| Layer | Responsibility | Key files |
|-------|----------------|-----------|
| `api/` | HTTP/WebSocket surface, request validation, DI wiring | `main.py`, `routers/*`, `schemas/*`, `dependencies.py` |
| `services/` | Business logic; orchestrate repos + external clients | `giveaway_service.py`, `game_service.py`, `settings_service.py`, `notification_service.py`, `scheduler_service.py` |
| `repositories/` | Data access; one per entity over a `BaseRepository` | `base.py`, `giveaway.py`, `entry.py`, `game.py`, `activity_log.py`, `settings.py` |
| `utils/` | External I/O: SteamGifts scraping, Steam store API | `steamgifts_client.py`, `steam_client.py` |
| `models/` | SQLAlchemy 2.0 ORM models | `giveaway.py`, `game.py`, `entry.py`, `activity_log.py`, `settings.py`, `scheduler_state.py` |
| `workers/` | Scheduled background automation | `automation.py`, `processor.py`, `scanner.py`, `safety_checker.py`, `scheduler.py` |
| `core/` | Cross-cutting: config, event bus, logging, exceptions | `config.py`, `events.py`, `logging.py`, `exceptions.py` |
| `db/` | Async engine, session factory, migrations | `session.py`, `alembic/` |

### Data model

Six entities, two of them singletons (always `id=1`):

- **Giveaway** — a scraped giveaway: `code`, `game_name`, `price`, `end_time`,
  `is_entered`, `is_hidden`, `is_wishlist`, `is_won`, `is_safe`/`safety_score`,
  the last cycle's `eligibility_reason`/`eligibility_detail`/`eligibility_checked_at`,
  FK → Game.
- **Game** — Steam store metadata: `review_score`, `total_reviews`,
  `release_date`, `header_image`, `type`, `genres`/`categories` (JSON lists of
  Steam `appdetails` description strings; NULL = not fetched yet, `[]` = Steam
  returned none).
- **Entry** — a record that we entered a giveaway: `points_spent`, `entry_type`
  (`auto`/`manual`/`wishlist`), `status`.
- **ActivityLog** — append-only event/audit feed surfaced in the UI.
- **Settings** (singleton) — all user config incl. `phpsessid`,
  `excluded_genres` and `included_genres` (JSON lists, default `[]`) and
  `autojoin_priorities` (ordered JSON list, 0 to 3 items).
- **SchedulerState** (singleton) — runtime counters: `total_scans`,
  `total_entries`, `total_errors`, `last_scan_at`, `next_scan_at`.

---

## 3. Two runtime entry points

The backend is driven from two directions that share the same service layer:

### a) Synchronous — the REST/WebSocket API

`api/main.py` builds the FastAPI app, mounts routers under `/api/v1/*`, and the
WebSocket under `/ws`. Per request, `dependencies.py` opens a DB session
(`get_db`), constructs the needed services (each with freshly-started HTTP
clients), and hands them to the router. Responses are ORM → Pydantic DTOs.

The event bus (`core/events.py::event_manager`) lets services/workers
`broadcast_event(...)`; the WebSocket router relays those to connected browsers
for live updates.

### b) Asynchronous — the scheduler

On startup (`lifespan` in `main.py`), if `automation_enabled`:

1. `scheduler_manager.start()` — a singleton wrapper around APScheduler's
   `AsyncIOScheduler` (`workers/scheduler.py`).
2. Register **`automation_cycle`** as an interval job every
   `scan_interval_minutes` (default 30).
3. Register **`safety_check_cycle`** every 45s (if `safety_check_enabled`).
4. **Win checks** are scheduled dynamically: after a cycle enters anything,
   `SchedulerService.schedule_next_win_check()` adds a one-shot date job timed
   to just after the soonest-expiring entered giveaway ends.

---

## 4. The core automation workflow

This is the heart of the system: one run of `workers/automation.py::automation_cycle()`.

```mermaid
flowchart TD
    A[automation_cycle every N min] --> B{phpsessid set?}
    B -- no --> Z[skip: not authenticated]
    B -- yes --> C[open session + start sg_client/steam_client + build services]
    C --> D[Step 1: sync_giveaways regular]
    D --> E[Step 2: sync_giveaways wishlist]
    E --> F[Step 2.5: sync DLC if enabled]
    F --> G[Step 3: sync_wins]
    G --> H[Step 3.5: sync_entered_giveaways]
    H --> H2[Step 3.75: safety sweep]
    H2 --> H3[Step 3.9: refresh_stale_games, bounded batch]
    H3 --> I{autojoin_enabled?}
    I -- no --> K[skip entries]
    I -- yes --> J[_process_entries]
    J --> L{entered > 0?}
    L -- yes --> M[schedule_next_win_check]
    L -- no --> N[broadcast automation_cycle_completed]
    K --> N
    M --> N
    N --> O[close clients]
```

**`sync_giveaways` (the scrape + cache step):**

```
steamgifts_client.get_giveaways(page)        # scrape HTML (BeautifulSoup)
  → for each giveaway:
      game_service.get_or_fetch_game(...)     # Steam store API enrichment
      giveaway_repo.upsert(...)               # cache in SQLite
```

**`_process_entries` (the entry step):**

```
policy_from_settings(settings)               # InvalidPolicyError → log_error, nothing entered
points = giveaway_service.fetch_points()
decide_cycle(policy, points)                 # decide + persist reason/detail for the whole pool
  → plan_cycle: points_accumulating / budget_floor / cycle_cap on the ordered enter list
  → for each planned giveaway (sequential):
      sleep(entry_delay_min..max)              # human-like pacing, none before the first
      giveaway_service.enter_giveaway(code)    # refresh xsrf → POST → record Entry
      record_outcomes(...)                     # what actually happened; running balance re-checked
      broadcast entry_success / entry_failed
```

**Eligibility (`services/eligibility.py`):** this module is the one definition
of the auto-join decision; there is no SQL mirror. A giveaway passes four
gates (`expired`, `hidden`, `entered`, `unsafe`), is matched against the
ordered `autojoin_priorities`, and, unless an exempt priority (wishlist or DLC)
lifts it, runs the filter chain (`price_below_min`, `genre_excluded`,
`genre_not_included`, `no_game_data`, `score_below_min`, `reviews_below_min`,
`game_too_old`). The gates run through one loop shared by `decide` and `gate_of`,
the gate-only view the entry loop uses to record an attempt the safety check
refused (`unsafe`, or `hidden` when `auto_hide_unsafe` is off) instead of `eligible`. `decide` returns a `Decision` with a code and a small detail
dict; `explain` renders it in the user's terms; `order_key` sorts the enter
list; `CycleBudget`/`plan_cycle` add `budget_floor`, `cycle_cap` and
`points_accumulating`. The rules live in the `GATES`, `FILTERS` and `OUTCOMES`
tuples and `PRIORITY_TYPES`; `REASON_LABELS` and the data served by
`GET /giveaways/registry` (`registry_as_data`) are derived from them, so a new
rule is one entry there. Cycle results are stored on
`Giveaway.eligibility_reason`/`eligibility_detail`; `preview_policy` and the
`lens=autojoin` tab views evaluate live and persist nothing; they fill the game
fields from the same games query as the decisions. Genre matching
folds ASCII letters only. Unknown genres pass `excluded_genres` but fail a
non-empty `included_genres`. Only store genres are available; Steam's
user-voted tags are not in `appdetails`.

**Stale-game refresh (step 3.9):** each cycle `refresh_stale_games` refreshes at
most `GAME_REFRESH_BATCH_SIZE` (10) cached games, oldest first.
`Game.needs_refresh` and `GameRepository.get_stale_games` share one definition
of stale: never refreshed, older than 7 days, or `genres IS NULL` (rows cached
before genres were stored). The per-giveaway read-through fetch during sync
uses the narrower `is_stale_by_age`, so the genres backfill drains over cycles
instead of as a burst. Apps Steam reports unavailable get `last_refreshed_at`
advanced and NULL genres/categories set to `[]`, so they leave the queue. The
cycle result key `game_refresh` is `{refreshed, skipped: false}`, or
`{refreshed: 0, skipped: true, reason: "steam_rate_limited",
retry_after_seconds}` during the Steam cool-down, plus `error` on failure; it
is returned by `POST /scheduler/run` and broadcast with
`automation_cycle_completed`.

**Steam cool-down (`services/game_service.py::steam_cooldown`):** any Steam 429
(from `appdetails`, from `GetAppReviews` inside a save, or an `appdetails` body
that is not a JSON object) starts a process-wide 180 s cool-down. While it
runs no Steam lookup is sent: cached rows are served, uncached apps get no row
(filters needing game data report `no_game_data` until a later cycle), the
batch refresh returns 0 and stops on the first 429, and `GET /games/{app_id}`
answers 429 `STEAM_003` for uncached apps. Requests sent inside Steam's per-IP
throttle extend it, hence the pause. `appdetails` is requested with
`l=english` so genre names are one vocabulary. Review scores come from
`GET api.steampowered.com/IUserReviewsService/GetAppReviews/v1/` (public, no
key; `input_json` carries only `appid` and `num_per_page: 1`, so Steam's
default languages and purchase type apply). Any non-200 answer, invalid
JSON, or a `query_summary` field that is not a plain integer in range (score
0–9, counts 0–2³¹−1; `REVIEW_SUMMARY_LIMITS` in `utils/steam_client.py`) is a
failure, never "no reviews"; "no reviews" is a 200 without `query_summary`. A
failed call keeps the cached review fields instead of zeroing them, and what
happens to `last_refreshed_at` depends on the row:

- throttled (429): unchanged, so the row is retried once the cool-down ends;
- failed, row with cached reviews (`total_reviews > 0`): stamped now, and the
  refresh counts as completed;
- failed, row without cached reviews (placeholder zeros): stamped
  `now − 7 d + REVIEW_RETRY_DELAY` (6 h), so the zeros are never served as
  fresh, the row is due again after 6 h behind the rows already stale (rows
  whose reviews keep failing rotate instead of holding every
  `refresh_stale_games` slot), and `refresh_game` reports `failed`;
- new row, reviews failed: saved with zeros and `last_refreshed_at` NULL, so
  `refresh_stale_games` retries it first.

**Safety check (separate background job, `safety_check_cycle`, every 45s):**

```
giveaway_repo.get_unchecked_eligible(limit=1) # is_safe IS NULL
  → check_giveaway_safety(code)               # scrape description, score it
  → if unsafe: hide_on_steamgifts(code)        # → is_hidden = True
```

The safety job and the entry job are **decoupled**: safety relies on hiding
unsafe giveaways so the entry step's `unsafe`/`hidden` gates skip them. See §6 for why this doesn't actually protect entries in practice.

---

## 5. Component reference

| Component | Role | Notes |
|-----------|------|-------|
| `SteamGiftsClient` | Scrapes giveaways/wins/entered pages; enters/hides giveaways; manages xsrf token & session | No retry/backoff/rate-limit; brittle CSS selectors |
| `SteamClient` | Steam store API for game metadata | Has rate limiter + retry/backoff; `appdetails` pinned to `l=english`; a non-object body raises `SteamAPIRateLimitError` |
| `GiveawayService` | Sync giveaways/wins/entered, eligibility, enter, safety check, hide | The largest service; the orchestration hub |
| `GameService` | Fetch/cache game metadata (incl. genres/categories), bounded stale refresh, genre counts, review tiers | Owns the shared Steam cool-down; `lookup_game` returns the row plus a `FetchStatus` (None on a cache hit) |
| `SettingsService` | Read/write the Settings singleton | |
| `NotificationService` | Write ActivityLog entries + broadcast events | |
| `SchedulerService` | Scheduler control (start/stop/pause), state/stats, **win-check scheduling** | |
| `SchedulerManager` | Singleton wrapper over APScheduler | Mirrors `is_running`/`is_paused` as its own state |
| `event_manager` | In-process pub/sub → WebSocket | |

---

## 6. Automation-layer consolidation (done)

The layering was always sound, but the automation layer had grown three
overlapping implementations of the same work plus a two-part safety design that
protected little. That redundancy has now been consolidated. Below is what
changed and why.

### 6.1 One "scan and enter" engine, shared by the manual triggers

Every job now bootstraps through `automation_context()` and the manual triggers
delegate to the same shared steps the scheduled cycle uses.

| Code path | How it's reached | State |
|-----------|------------------|-------|
| `workers/automation.py::automation_cycle` + `processor._process_entries` | scheduled job **and** `/run` | the single engine |
| `workers/processor.py::process_giveaways` | `/process` | thin wrapper → opens context, delegates to `_process_entries` |
| `workers/scanner.py::scan_giveaways` / `quick_scan` | `/scan`, `/scan/quick` | thin wrappers over `sync_giveaways` via the context |
| `workers/automation.py::sync_wins_only` | `/sync-wins` | thin wrapper over the context |
| `services/scheduler_service.py::run_automation_cycle` | — | **removed** (was dead and raised `TypeError`) |

The four manual triggers are all still exposed (the frontend calls `/run`,
`/scan`, `/process`, `/sync-wins`) — they're just thin wrappers now instead of
parallel re-implementations.

### 6.2 Client/service bootstrap lives in one factory

The previously copy-pasted block — "start `sg_client`, start `steam_client`,
build the services, `try/finally close`" — is now `workers/context.py`:

```python
async with automation_context() as ctx:   # yields session + ready services
    if not ctx.authenticated:              # no PHPSESSID → services are None
        return {"skipped": True, "reason": "not_authenticated"}
    await ctx.giveaway_service.sync_giveaways(...)
# clients + session closed automatically
```

When unauthenticated it yields a context with `authenticated=False` and no
clients started, so callers share one skip path.

### 6.3 Safety is now synchronous and inline

The background `safety_check_cycle` job is **deleted**. When
`settings.safety_check_enabled` is set, the entry loop calls
`enter_giveaway_with_safety_check` (check → hide if unsafe → enter) per giveaway,
so unsafe giveaways are never entered. This removes the racing 1-per-45s job and
its "assume safe on error" bug. Cost: one extra HTTP fetch per entry —
negligible against the existing 5–15s inter-entry sleep. Eligibility
(`services/eligibility.py`) keys on `is_hidden`/`is_entered` and, through the `unsafe`
gate, on `is_safe is False` (`is_safe` None passes on to the filters), so dropping the
background job did not change which giveaways pass; inline hiding keeps unsafe
giveaways out of future eligible lists.

### 6.4 `SchedulerService` is now cohesive

With `run_automation_cycle` gone it does exactly three related things: scheduler
control passthrough, state/stats persistence, and win-check scheduling.

### 6.5 One Alembic migration tree

The orphaned, stale `src/db/migrations/` tree is **deleted**; `src/alembic/` is
the only migration tree (`pyproject.toml` package list updated to match).

---

## 7. Resulting shape (engine)

```
workers/
  context.py     # automation_context(): the one bootstrap factory
  automation.py  # automation_cycle(): the only orchestrator (scheduled + /run)
                 # sync_wins_only(): thin /sync-wins wrapper
  processor.py   # _process_entries(): the only entry loop (inline safety)
                 # process_giveaways(): thin /process wrapper
                 # enter_single_giveaway(): thin /enter wrapper
  scanner.py     # scan_giveaways()/quick_scan(): thin /scan wrappers
  scheduler.py   # SchedulerManager (unchanged)
                 # safety_checker.py REMOVED — safety is inline at entry

services/
  scheduler_service.py   # control + state + win-check ONLY
```

Net effect: **one** automation path, **one** bootstrap, **one** safety mechanism
(synchronous), and the dead `TypeError` path plus the orphan migration tree
gone. No layer boundaries changed — this was consolidation within the
workers/scheduler area, not a rewrite.
