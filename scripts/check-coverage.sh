#!/usr/bin/env bash
# Coverage gate for a change: lines added or modified relative to a base ref
# must be covered at least FAIL_UNDER percent.
#
#   scripts/check-coverage.sh [base-ref] [fail-under]     # default origin/master 95
#
# Backend: pytest-cov over backend/src (run from backend/ so the pyproject
# addopts apply), judged by diff-cover on the Cobertura XML.
# Frontend: vitest v8 coverage (the lcov reporter is configured in
# vitest.config.ts), judged by diff-cover over the logic modules only
# (src/hooks, src/services, src/stores, src/utils); components and pages are
# left to the reviewers. diff-cover ignores --src-root for lcov input, so the
# SF: paths are prefixed with frontend/ to match the paths git reports.
set -uo pipefail
BASE="${1:-origin/master}"
MIN="${2:-95}"
cd "$(dirname "$0")/.."
DIFF_COVER="$(pwd)/backend/.venv/bin/diff-cover"
if [ ! -x "$DIFF_COVER" ]; then
  echo "diff-cover is not installed: run  backend/.venv/bin/pip install -e 'backend[dev]'"
  exit 2
fi
status=0

echo "== backend: pytest --cov (diff vs $BASE, fail-under $MIN%)"
(cd backend && .venv/bin/python -m pytest -q --cov=src --cov-report=xml:coverage.xml --cov-report= | tail -n 3) \
  || { echo "backend tests failed"; status=1; }
"$DIFF_COVER" backend/coverage.xml --compare-branch="$BASE" --fail-under="$MIN" || status=1

echo
echo "== frontend: vitest --coverage (diff vs $BASE, fail-under $MIN%)"
npm --prefix frontend run -s test:coverage >/dev/null 2>&1 || { echo "vitest coverage run failed"; status=1; }
if [ -f frontend/coverage/lcov.info ]; then
  prefixed=$(mktemp)
  sed 's#^SF:#SF:frontend/#' frontend/coverage/lcov.info > "$prefixed"
  # One --include with all patterns: a repeated flag keeps only the last one.
  "$DIFF_COVER" "$prefixed" --compare-branch="$BASE" --fail-under="$MIN" \
    --include 'frontend/src/hooks/**' 'frontend/src/services/**' 'frontend/src/stores/**' 'frontend/src/utils/**' \
    || status=1
  rm -f "$prefixed"
else
  echo "no frontend coverage report produced"; status=1
fi
exit $status
