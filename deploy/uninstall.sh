#!/usr/bin/env bash
# Stop and remove the Quorum runner systemd service.
set -euo pipefail

echo "Stopping quorum-runner.service ..."
systemctl stop quorum-runner.service 2>/dev/null || true
systemctl disable quorum-runner.service 2>/dev/null || true
rm -f /etc/systemd/system/quorum-runner.service
systemctl daemon-reload

echo "Done. Service removed."
