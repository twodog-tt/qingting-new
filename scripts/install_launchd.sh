#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.twodog.qingting-daily"
SRC="$ROOT/scripts/com.twodog.qingting-daily.plist"
DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"

mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$ROOT/logs"
chmod +x "$ROOT/scripts/daily_publish.sh"

# 确保 plist 中的路径与当前项目一致
sed "s|/Users/wangxintong/qingting-new|${ROOT}|g" "$SRC" > "$DEST"

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
launchctl enable "gui/$(id -u)/${LABEL}"

echo "Installed LaunchAgent: $DEST"
echo "Schedule: every day 10:00 (system timezone)"
echo "Logs: $ROOT/logs/"
if [[ ! -f "$ROOT/.env" ]]; then
  echo
  echo "WARNING: 缺少 $ROOT/.env"
  echo "请执行: cp .env.example .env  并填入 BRIEF_LLM_API_KEY"
fi
launchctl print "gui/$(id -u)/${LABEL}" 2>/dev/null | head -n 20 || true
