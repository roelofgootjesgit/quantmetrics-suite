#!/usr/bin/env bash
# Run QuantBuild CLI with the same env as QuantOS (quantmetrics_os/orchestrator .env).
# Use this on the VPS when you normally keep CTRADER_* in orchestrator/.env but
# start manually from quantbuildv1 — plain `python -m ...` does NOT load that file.
#
# Usage (from anywhere):
#   /root/dev/quant/quantbuildv1/scripts/vps/run_live.sh --config configs/demo_strict_ctrader.yaml live --dry-run
#
# Env:
#   QUANTBUILD_ROOT       — override checkout (default: repo root containing this script)
#   QUANTBUILD_ORCHESTRATOR_ENV — explicit path to orchestrator/.env
#   PYTHON                — override interpreter (default: $ROOT/.venv/bin/python)
set -euo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_ROOT="${QUANTBUILD_ROOT:-$(cd "$_SCRIPT_DIR/../.." && pwd)}"
cd "$_ROOT"

_ORCH_EXPLICIT="${QUANTBUILD_ORCHESTRATOR_ENV:-}"
_ORCH_CANDIDATES=(
  "$_ORCH_EXPLICIT"
  "$_ROOT/../quantmetrics_os/orchestrator/.env"
  "/root/dev/quant/quantmetrics_os/orchestrator/.env"
)

_sourced=""
for _c in "${_ORCH_CANDIDATES[@]}"; do
  [[ -z "$_c" ]] && continue
  if [[ -f "$_c" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$_c"
    set +a
    _sourced="$_c"
    break
  fi
done

if [[ -n "$_sourced" ]]; then
  echo "run_live: loaded environment from $_sourced" >&2
else
  echo "run_live: no orchestrator .env found; using shell + quantbuildv1/.env only (python-dotenv)." >&2
  echo "run_live: set QUANTBUILD_ORCHESTRATOR_ENV or create ../quantmetrics_os/orchestrator/.env (QuantOS)" >&2
fi

_PY="${PYTHON:-${_ROOT}/.venv/bin/python}"
export PYTHONPATH="${_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
exec "$_PY" -m src.quantbuild.app "$@"
