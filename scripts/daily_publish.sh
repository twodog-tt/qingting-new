#!/usr/bin/env bash
# 本地每日发布：生成近24h日报（含 LLM 短评）→ 提交 site/ → 推送到 GitHub
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily_publish_$(date +%Y%m%d).log"

exec >>"$LOG_FILE" 2>&1
echo "======== $(date '+%Y-%m-%d %H:%M:%S %Z') start ========"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

if [[ -z "${BRIEF_LLM_API_KEY:-}${OPENAI_API_KEY:-}" ]]; then
  echo "ERROR: 未设置 BRIEF_LLM_API_KEY 或 OPENAI_API_KEY（请写入项目根目录 .env）"
  exit 2
fi

PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: 未找到 $PYTHON ，请先: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

"$PYTHON" -m brief publish --hours 24 --picks 8 --keep-days 7 --site site

git add site/
if git diff --staged --quiet; then
  echo "No site/ changes; skip commit"
else
  DATE_CN="$(TZ=Asia/Shanghai date +%F)"
  git commit -m "chore: publish daily brief ${DATE_CN}"
  git push origin HEAD
  echo "Pushed site/ to origin"
fi

echo "======== $(date '+%Y-%m-%d %H:%M:%S %Z') done ========"
