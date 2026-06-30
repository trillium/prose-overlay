#!/usr/bin/env bash
# Regenerate PYTHON_REPORT.md from the current state of prose_overlay_*.py.
# Uses uvx so radon + vulture don't need to be installed.

set -euo pipefail

cd "$(dirname "$0")/.."
OUT=PYTHON_REPORT.md
TMP=$(mktemp)

# Keep the hand-written header (everything before the first "---" separator)
# and replace only the raw analyzer output below it.
awk '/^---$/ {exit} {print}' "$OUT" > "$TMP"
echo "---" >> "$TMP"
echo "" >> "$TMP"

{
  echo "## radon — cyclomatic complexity (CC)"
  echo ""
  echo '```'
  uvx radon cc -a -s --no-assert --total-average prose_overlay*.py
  echo '```'
  echo ""
  echo "## radon — maintainability index (MI)"
  echo ""
  echo '```'
  uvx radon mi -s prose_overlay*.py
  echo '```'
  echo ""
  echo "## radon — raw LOC stats"
  echo ""
  echo '```'
  uvx radon raw -s prose_overlay*.py | tail -100
  echo '```'
  echo ""
  echo "## vulture — dead code (confidence ≥ 70%)"
  echo ""
  echo '```'
  uvx vulture --min-confidence 70 prose_overlay*.py || true
  echo '```'
} >> "$TMP"

mv "$TMP" "$OUT"
echo "wrote $OUT ($(wc -l < "$OUT") lines)"
