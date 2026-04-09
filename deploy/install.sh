#!/usr/bin/env bash
# Install and start the Quorum runner as a systemd service.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/quorum-runner.service"
TARGET="/etc/systemd/system/quorum-runner.service"

if [[ ! -f "$SERVICE_FILE" ]]; then
  echo "ERROR: $SERVICE_FILE not found" >&2
  exit 1
fi

echo "Installing quorum-runner.service ..."
cp "$SERVICE_FILE" "$TARGET"
systemctl daemon-reload
systemctl enable quorum-runner.service
systemctl start quorum-runner.service

echo "Done. Check status with:"
echo "  systemctl status quorum-runner"
echo "  journalctl -u quorum-runner -f"
echo "  cat /root/Quorum/data/runner_metrics.json"
