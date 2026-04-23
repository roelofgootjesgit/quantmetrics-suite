#!/usr/bin/env bash
# Chain validate-events, summarize-day, check-ingest-health, score-run (Linux/macOS/VPS).
# From repo root:
#   export PYTHONPATH="$PWD/src"   # optional; script sets it relative to repo
#   bash scripts/nightly_quantlog_report.sh /path/to/quantlog_events/2026-04-01 [max_gap_seconds] [pass_threshold]
#
# Exit codes: worst of validate (1 on errors), ingest-health (3 if gaps), score-run (4 if below threshold).
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="${REPO_ROOT}/src"
cd "$REPO_ROOT" || exit 1

DAY_PATH="${1:?usage: $0 <event-folder> [max_gap_seconds] [pass_threshold]}"
MAX_GAP="${2:-300}"
PASS_TH="${3:-95}"
worst=0
ec=0

echo "=== validate-events ==="
ec=0
python -m quantlog.cli validate-events --path "$DAY_PATH" || ec=$?
[ "$ec" -gt "$worst" ] && worst=$ec

echo "=== summarize-day ==="
python -m quantlog.cli summarize-day --path "$DAY_PATH" || true

echo "=== check-ingest-health ==="
ec=0
python -m quantlog.cli check-ingest-health --path "$DAY_PATH" --max-gap-seconds "$MAX_GAP" || ec=$?
[ "$ec" -gt "$worst" ] && worst=$ec

echo "=== score-run ==="
ec=0
python -m quantlog.cli score-run --path "$DAY_PATH" --max-gap-seconds "$MAX_GAP" --pass-threshold "$PASS_TH" || ec=$?
[ "$ec" -gt "$worst" ] && worst=$ec

echo "=== done (exit $worst): validate/ingest/score combined ==="
exit "$worst"
