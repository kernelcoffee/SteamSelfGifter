# Technical Debt & Known Issues

This document tracks disabled warnings, skipped tests, and other technical debt that should be addressed in the future.

## ESLint Rules Disabled

### Frontend (`frontend/eslint.config.js`)

None - `react-hooks/set-state-in-effect` was re-enabled after refactoring
`Settings.tsx` (form initializes from loaded data in an inner component,
remounted via `key` on refetch) and `Dashboard.tsx` (countdown derived during
render, driven by a tick interval).

## Skipped Tests

### Backend

| Test File | Tests Skipped | Reason |
|-----------|---------------|--------|
| `integration/*` | All | Requires `--run-integration` flag and valid PHPSESSID |

**Test counts (as of last run):**
- Backend: 759 passed, 0 skipped (integration tests excluded; they need `--run-integration` + a valid PHPSESSID)
- Frontend: 170 passed, 0 skipped

## Future Improvements

### Code Quality

- [x] Re-enable `react-hooks/set-state-in-effect` after refactoring affected components
- [x] Fix APScheduler event loop conflicts to enable scheduler e2e tests in CI (fixed by the automation-layer consolidation)
- [x] Add more integration test coverage with mocked external services
      (`tests/integration_mocked/` — real clients through `httpx.MockTransport`,
      runs in CI; both clients take an optional `transport` for this)

### Dependency Notes

- **APScheduler stays on 3.x** (evaluated 2026-07-12): 4.0 has never shipped a
  stable release (PyPI latest is 3.11.x), and the event-loop conflicts that
  motivated the upgrade were fixed by the automation-layer consolidation
  (scheduler e2e tests run, 0 skips). The `apscheduler>=3.11.0,<4` pin in
  `backend/pyproject.toml` is deliberate; revisit if a stable 4.x appears.
