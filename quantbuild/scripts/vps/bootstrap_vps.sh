#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/vps/bootstrap_vps.sh <quantbuild_repo_url> <quantbridge_repo_url>
#
# Example:
#   ./scripts/vps/bootstrap_vps.sh \
#     git@github.com:you/quantbuild.git \
#     git@github.com:you/quantbridge.git

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <quantbuild_repo_url> <quantbridge_repo_url>"
  exit 1
fi

QB_REPO_URL="$1"
BRIDGE_REPO_URL="$2"

BASE_DIR="/opt/quantbuild"
QB_DIR="${BASE_DIR}/quantbuild"
BRIDGE_DIR="${BASE_DIR}/quantbridge"

sudo apt update
sudo apt install -y git python3 python3-venv python3-pip ripgrep

sudo mkdir -p "${BASE_DIR}"
sudo chown -R "$USER:$USER" "${BASE_DIR}"

if [[ ! -d "${QB_DIR}/.git" ]]; then
  git clone "${QB_REPO_URL}" "${QB_DIR}"
else
  echo "quantbuild repo already present: ${QB_DIR}"
fi

if [[ ! -d "${BRIDGE_DIR}/.git" ]]; then
  git clone "${BRIDGE_REPO_URL}" "${BRIDGE_DIR}"
else
  echo "quantBridge repo already present: ${BRIDGE_DIR}"
fi

cd "${QB_DIR}"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "Bootstrap complete."
echo "Next: configure /etc/quantbuild/quantbuild.env and install systemd service."
