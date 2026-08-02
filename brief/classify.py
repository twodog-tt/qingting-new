"""Load sources.yaml and apply category / topic tagging rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from brief import CONFIG_PATH, CATEGORIES


def homepage_from_url(url: str) -> str:
    """Best-effort site root from an article or feed URL."""
    if not url:
        return ""
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url
    return f"{parsed.scheme}://{parsed.netloc}/"


@dataclass
class Source:
    id: str
    name: str
    url: str
    default_category: str
    region_tags: list[str] = field(default_factory=list)
    enabled: bool = True
    note: str | None = None
    home: str = ""

    @property
    def home_url(self) -> str:
        return self.home or homepage_from_url(self.url)


@dataclass
class BriefConfig:
    sources: list[Source]
    policy_keywords: list[str]
    finance_keywords: list[str]
    tech_keywords: list[str]
    tag_labels: dict[str, str]


def load_config(path: Path | None = None) -> BriefConfig:
    cfg_path = path or CONFIG_PATH
    raw: dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    sources: list[Source] = []
    for item in raw.get("sources") or []:
        cat = item.get("default_category", "finance")
        if cat not in CATEGORIES:
            cat = "finance"
        sources.append(
            Source(
                id=item["id"],
                name=item["name"],
                url=item["url"],
                default_category=cat,
                region_tags=list(item.get("region_tags") or []),
                enabled=bool(item.get("enabled", True)),
                note=item.get("note"),
                home=(item.get("home") or "").strip(),
            )
        )

    classification = raw.get("classification") or {}
    return BriefConfig(
        sources=sources,
        policy_keywords=list(classification.get("policy_keywords") or []),
        finance_keywords=list(classification.get("finance_keywords") or []),
        tech_keywords=list(classification.get("tech_keywords") or []),
        tag_labels=dict(raw.get("tag_labels") or {}),
    )


def _contains_any(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    for kw in keywords:
        if kw.lower() in lower:
            return True
    return False


def classify_article(
    title: str,
    summary: str,
    default_category: str,
    config: BriefConfig,
) -> str:
    """Return tech | finance | policy. Keyword overrides beat source default."""
    blob = f"{title}\n{summary}"
    if _contains_any(blob, config.policy_keywords):
        return "policy"
    if _contains_any(blob, config.finance_keywords):
        return "finance"
    if _contains_any(blob, config.tech_keywords):
        return "tech"
    if default_category in CATEGORIES:
        return default_category
    return "finance"


def topic_labels(
    region_tags: list[str],
    title: str,
    summary: str,
    config: BriefConfig,
) -> list[str]:
    """Chinese topic chips derived from source tags + title/summary hits."""
    labels: list[str] = []
    seen: set[str] = set()

    def add(tag: str) -> None:
        label = config.tag_labels.get(tag, tag)
        if label not in seen:
            seen.add(label)
            labels.append(label)

    for tag in region_tags:
        add(tag)

    blob = f"{title}\n{summary}".lower()
    keyword_to_tag = [
        (["bitcoin", "btc", "ethereum", "crypto", "比特币", "加密"], "crypto"),
        (["nasdaq", "dow", "s&p", "wall street", "美股"], "us"),
        (["a股", "上证", "深证", "沪深", "a-share"], "cn"),
        (["港股", "hang seng", "hsi", "hong kong"], "hk"),
        (["kospi", "韩股", "samsung", "korea"], "kr"),
        (["nikkei", "日股", "tokyo", "yen"], "jp"),
        (["forex", "fx", "汇率", "usd/cny", "dollar"], "fx"),
        (["gold", "黄金", "xau"], "gold"),
        (["oil", "crude", "wti", "brent", "原油"], "oil"),
    ]
    for kws, tag in keyword_to_tag:
        if any(k in blob for k in kws):
            add(tag)

    return labels
