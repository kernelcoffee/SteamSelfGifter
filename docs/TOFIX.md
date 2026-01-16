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
| `test_api_main.py` | 2 | Requires database setup - covered by e2e tests |
| `test_scheduler_api.py` | 12 (entire file) | APScheduler causes event loop conflicts in test suite - covered by unit tests |
| `integration/*` | All | Requires `--run-integration` flag and valid PHPSESSID |

**Test counts (as of last run):**
- Backend: 718 passed, 31 skipped
- Frontend: 170 passed, 0 skipped

## Future Improvements

### Higher Risk Upgrades (Deferred)

| Package | Current | Latest | Notes |
|---------|---------|--------|-------|
| Tailwind CSS | 3.x | 4.x | Major config format changes |
| react-router-dom | 6.x | 7.x | API changes, migration guide available |

### Code Quality

- [ ] Re-enable `react-hooks/set-state-in-effect` after refactoring affected components
- [ ] Fix APScheduler event loop conflicts to enable scheduler e2e tests in CI
- [ ] Add more integration test coverage with mocked external services