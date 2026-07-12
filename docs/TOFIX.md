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
- [ ] Add more integration test coverage with mocked external services
