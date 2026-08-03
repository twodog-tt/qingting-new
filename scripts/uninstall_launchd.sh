#!/usr/bin/env bash
set -euo pipefail

LABEL="com.twodog.qingting-daily"
DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "$DEST"
echo "Removed LaunchAgent: $LABEL"
