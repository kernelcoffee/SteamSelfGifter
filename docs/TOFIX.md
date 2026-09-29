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
- Backend: 851 passed, 17 skipped (the skips are the `integration/*` files; they need `--run-integration` + a valid PHPSESSID)
- Frontend: 182 passed, 0 skipped

## Future Improvements

### Code Quality

- [x] Re-enable `react-hooks/set-state-in-effect` after refactoring affected components
- [x] Fix APScheduler event loop conflicts to enable scheduler e2e tests in CI (fixed by the automation-layer consolidation)
- [x] Add more integration test coverage with mocked external services
      (`tests/integration_mocked/` — real clients through `httpx.MockTransport`,
      runs in CI; both clients take an optional `transport` for this)

### Dependency Notes

- **TypeScript stays on 6.x** (evaluated 2026-09-29): 7.0 is the native Go
  compiler and ships no compiler API yet, and typescript-eslint 8.71 declares
  support for `<6.1.0` only, so typed linting would break. Revisit once
  typescript-eslint supports 7.x (TS 7.1 is slated to bring the API back).
- **jest-dom Vitest 5 type shim** (added 2026-09-29): jest-dom 7.0.1 augments
  Vitest's old single-parameter `Assertion<T>`, which no longer merges with
  Vitest 5's `Assertion<R, T>`. `frontend/src/test/jest-dom.d.ts` bridges the
  matcher types through Vitest's `Matchers<R, T>` extension point. Delete it
  once jest-dom ships Vitest 5 support
  (https://github.com/testing-library/jest-dom/issues/738).
- **Starlette 1.x TestClient deprecation**: FastAPI 0.141 pulls starlette 1.7,
  whose `TestClient` warns that using it over `httpx` is deprecated in favour
  of `httpx2`. Harmless for now; migrate the test client when FastAPI's own
  `TestClient` moves.
- **APScheduler stays on 3.x** (evaluated 2026-07-12): 4.0 has never shipped a
  stable release (PyPI latest is 3.11.x), and the event-loop conflicts that
  motivated the upgrade were fixed by the automation-layer consolidation
  (scheduler e2e tests run, 0 skips). The `apscheduler>=3.11.0,<4` pin in
  `backend/pyproject.toml` is deliberate; revisit if a stable 4.x appears.
