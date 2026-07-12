# Technical Debt & Known Issues

This document tracks disabled warnings, skipped tests, and other technical debt that should be addressed in the future.

## ESLint Rules Disabled

### Frontend (`frontend/eslint.config.js`)

| Rule | Reason | Files Affected |
|------|--------|----------------|
| `react-hooks/set-state-in-effect` | False positives for valid patterns (initializing form state from fetched data, countdown timers) | `Settings.tsx`, `Dashboard.tsx` |

**Details:**
- `Settings.tsx`: Initializes form state when settings data is fetched - standard pattern for forms with async data
- `Dashboard.tsx`: Updates countdown timer state every second - valid use of setInterval in useEffect

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

- [ ] Re-enable `react-hooks/set-state-in-effect` after refactoring affected components
- [x] Fix APScheduler event loop conflicts to enable scheduler e2e tests in CI (fixed by the automation-layer consolidation)
- [ ] Add more integration test coverage with mocked external services
