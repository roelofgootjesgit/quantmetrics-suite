#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="quantbuild-ctrader-demo.service"
LOG_FILE="/opt/quantbuild/quantbuildv1/logs/runtime_ctrader_demo.log"

echo "=== service status ==="
sudo systemctl status "${SERVICE_NAME}" --no-pager | sed -n '1,20p'

echo
echo "=== critical log scan (last 24h file view) ==="
rg "BOOTSTRAP|decision_cycle|market_data_bootstrap_failed|live_data_refresh_fail_fast|ERROR" "${LOG_FILE}" | tail -n 120

echo
echo "=== fail-fast occurrences ==="
rg "live_data_refresh_fail_fast" "${LOG_FILE}" | tail -n 20 || true

echo
echo "=== recent decision cycles ==="
rg "decision_cycle" "${LOG_FILE}" | tail -n 40 || true
