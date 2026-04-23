#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash ops/vps/install_paper_service.sh"
  exit 1
fi

SERVICE_NAME="quantbridge-paper.service"
SRC_SERVICE="${1:-ops/vps/quantbridge-paper.service}"
DST_SERVICE="/etc/systemd/system/${SERVICE_NAME}"

if [[ ! -f "${SRC_SERVICE}" ]]; then
  echo "Service file not found: ${SRC_SERVICE}"
  exit 1
fi

echo "Installing ${SERVICE_NAME}..."
cp "${SRC_SERVICE}" "${DST_SERVICE}"
chmod 644 "${DST_SERVICE}"

echo "Reloading systemd..."
systemctl daemon-reload

echo "Enabling ${SERVICE_NAME}..."
systemctl enable "${SERVICE_NAME}"

echo "Restarting ${SERVICE_NAME}..."
systemctl restart "${SERVICE_NAME}"

echo "Service status:"
systemctl --no-pager --full status "${SERVICE_NAME}" || true

echo "Done."
