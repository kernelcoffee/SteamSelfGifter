#!/usr/bin/env bash
# Shortcut audit for a change: lists suppressions, skipped or focused tests,
# swallowed errors, debt markers and weakened assertions that the change
# introduced relative to a base ref, and whether the number of tests dropped.
# Exit 1 when anything was found; the caller judges whether a hit is justified.
#
#   scripts/shortcut-audit.sh [base-ref]     # default origin/master
set -uo pipefail
BASE="${1:-origin/master}"
cd "$(dirname "$0")/.."
found=0

# Added lines: committed changes since the merge base plus the working tree,
# then untracked files in full.
# Only code and tests are audited; prose (docs, agent briefs) legitimately
# names these markers.
SCOPE=(backend frontend/src frontend/e2e scripts .github)
added() {
  git diff "$BASE" --unified=0 -- "${SCOPE[@]}" ':(exclude)**/package-lock.json' ':(exclude)scripts/shortcut-audit.sh' \
    | grep -aE '^\+[^+]' | sed 's/^+//'
  git ls-files --others --exclude-standard -- "${SCOPE[@]}" | grep -vE 'package-lock.json|shortcut-audit.sh|\.(svg|png|zip|jar)$' \
    | while read -r f; do grep -aH '' "$f"; done
}
PATTERN='noqa|type: ?ignore|as any|@ts-ignore|@ts-expect-error|eslint-disable|pytest\.mark\.skip|pytest\.mark\.xfail|\.skip\(|\.only\(|\bxit\(|\bxtest\(|except Exception:|except:$|except BaseException:|suppress\(Exception|catch *\{ *\}|catch *\([a-zA-Z_]*\) *\{ *\}|\bTODO\b|\bFIXME\b|\bHACK\b|\bXXX\b|time\.sleep\(|waitForTimeout\(|assert True\b|status_code in \(|# pragma: no cover'

echo "== shortcut markers in added lines (vs $BASE)"
hits=$(added | grep -nE "$PATTERN" || true)
if [ -n "$hits" ]; then echo "$hits"; found=1; else echo "(none)"; fi

echo
echo "== assertions removed (vs $BASE)"
removed=$(git diff "$BASE" --unified=0 -- backend/tests frontend/src frontend/e2e | grep -aE '^-[^-]' | grep -E '^-[[:space:]]*(assert |expect\()' || true)
if [ -n "$removed" ]; then echo "$removed"; found=1; else echo "(none)"; fi

echo
echo "== test counts (base -> now)"
count_py() { grep -rhoE '^\s*(async )?def test_' "$@" 2>/dev/null | wc -l; }
count_ts() { grep -rhoE '^\s*(it|test)\(' "$@" 2>/dev/null | wc -l; }
tmp=$(mktemp -d); git archive "$BASE" backend/tests frontend/src frontend/e2e 2>/dev/null | tar -x -C "$tmp" 2>/dev/null
bpy=$(count_py "$tmp/backend/tests"); npy=$(count_py backend/tests)
bts=$(count_ts "$tmp/frontend/src" "$tmp/frontend/e2e"); nts=$(count_ts frontend/src frontend/e2e)
rm -rf "$tmp"
echo "pytest: $bpy -> $npy   vitest+playwright: $bts -> $nts"
if [ "$npy" -lt "$bpy" ] || [ "$nts" -lt "$bts" ]; then echo "test count decreased"; found=1; fi
exit $found
