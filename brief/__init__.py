"""近 24 小时财经科技日报生成器。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "sources.yaml"
TEMPLATE_DIR = ROOT / "templates"
REPORTS_DIR = ROOT / "reports"

CATEGORIES = ("tech", "finance", "policy")
CATEGORY_LABELS = {
    "tech": "科技",
    "finance": "金融",
    "policy": "政策",
}
