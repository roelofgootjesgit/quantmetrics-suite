#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/opt/quantbuild/quantbuild_e1_v1"
SVC_SRC="${BASE_DIR}/deploy/systemd/quantbuild-quantlog-report.service"
TMR_SRC="${BASE_DIR}/deploy/systemd/quantbuild-quantlog-report.timer"
SVC_DST="/etc/systemd/system/quantbuild-quantlog-report.service"
TMR_DST="/etc/systemd/system/quantbuild-quantlog-report.timer"
NIGHTLY="${BASE_DIR}/scripts/vps/quantlog_nightly.sh"

for f in "$SVC_SRC" "$TMR_SRC" "$NIGHTLY"; do
  if [[ ! -f "$f" ]]; then
    echo "Missing: $f"
    exit 1
  fi
done

sudo chmod +x "$NIGHTLY"
sudo cp "$SVC_SRC" "$SVC_DST"
sudo cp "$TMR_SRC" "$TMR_DST"
sudo systemctl daemon-reload
sudo systemctl enable quantbuild-quantlog-report.timer
sudo systemctl start quantbuild-quantlog-report.timer

echo "QuantLog nightly timer installed."
echo "Check: sudo systemctl list-timers | grep quantlog"
echo "Manual run: sudo systemctl start quantbuild-quantlog-report.service"
echo "Logs: tail -n 80 ${BASE_DIR}/logs/quantlog_nightly.log"
