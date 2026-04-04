#!/usr/bin/env bash
# Run QuantLog validate/summarize/score for the previous UTC calendar day.
# Intended for systemd timer on Linux VPS (GNU date). See deploy/systemd/quantbuild-quantlog-report.*.
set -euo pipefail

ROOT="${QUANTBUILD_ROOT:-/opt/quantbuild/quantbuild_e1_v1}"
cd "$ROOT"
# shellcheck source=/dev/null
source .venv/bin/activate

CONFIG="${QUANTBUILD_POST_RUN_CONFIG:-configs/ctrader_quantbridge_openapi.yaml}"
DAY="$(date -u -d "yesterday" +%Y-%m-%d)"

exec python scripts/quantlog_post_run.py --config "$CONFIG" --date "$DAY" "$@"
