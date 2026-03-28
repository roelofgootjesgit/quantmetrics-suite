#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/opt/quantbuild/quantbuild_e1_v1"
ENV_DIR="/etc/quantbuild"
ENV_FILE="${ENV_DIR}/quantbuild.env"
SERVICE_SRC="${BASE_DIR}/deploy/systemd/quantbuild-ctrader-demo.service"
SERVICE_DST="/etc/systemd/system/quantbuild-ctrader-demo.service"

if [[ ! -f "${SERVICE_SRC}" ]]; then
  echo "Service template not found: ${SERVICE_SRC}"
  exit 1
fi

sudo mkdir -p "${ENV_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
  sudo cp "${BASE_DIR}/deploy/systemd/quantbuild.env.example" "${ENV_FILE}"
  echo "Created ${ENV_FILE} from example. Fill credentials before starting service."
fi

sudo cp "${SERVICE_SRC}" "${SERVICE_DST}"
sudo systemctl daemon-reload
sudo systemctl enable quantbuild-ctrader-demo.service

echo "Service installed."
echo "Next:"
echo "  1) sudo nano ${ENV_FILE}"
echo "  2) sudo systemctl start quantbuild-ctrader-demo.service"
echo "  3) sudo systemctl status quantbuild-ctrader-demo.service --no-pager"
