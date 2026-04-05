#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="quantbuild-ctrader-demo.service"
LOG_FILE="/opt/quantbuild/quantbuildv1/logs/runtime_ctrader_demo.log"

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"
sudo systemctl status "${SERVICE_NAME}" --no-pager

echo
echo "Follow logs:"
echo "  tail -f ${LOG_FILE}"
