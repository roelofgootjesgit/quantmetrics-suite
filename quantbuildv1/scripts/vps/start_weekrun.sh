#!/usr/bin/env bash
set -euo pipefail

# Defaults match docs; override on VPS e.g. QUANTBUILD_ROOT=/root/dev/quant/quantbuildv1
ROOT="${QUANTBUILD_ROOT:-/opt/quantbuild/quantbuildv1}"
SERVICE_NAME="${QUANTBUILD_SERVICE_NAME:-quantbuild-ctrader-demo.service}"
LOG_FILE="${QUANTBUILD_LOG_FILE:-${ROOT}/logs/runtime_ctrader_demo.log}"

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"
sudo systemctl status "${SERVICE_NAME}" --no-pager

echo
echo "Follow logs:"
echo "  tail -f ${LOG_FILE}"
echo "(Set QUANTBUILD_ROOT / QUANTBUILD_LOG_FILE if your install is not under /opt/quantbuild.)"
