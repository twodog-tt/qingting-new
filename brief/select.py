"""Select the day's most relevant articles for short commentary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from brief import CATEGORY_LABELS
from brief.fetch import Article

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _fmt_cn(dt: datetime) -> str:
    return dt.astimezone(TZ_SHANGHAI).strftime("%Y-%m-%d %H:%M")


# Theme weights for "what this brief cares about"
THEME_KEYWORDS: list[tuple[str, list[str], float]] = [
    ("加密", ["bitcoin", "btc", "ethereum", "eth", "crypto", "比特币", "以太坊", "加密", "stablecoin", "defi", "sec crypto"], 3.0),
    ("美股", ["nasdaq", "dow", "s&p", "s&p 500", "wall street", "美股", "federal reserve", "fed ", "fomc"], 2.5),
    ("A股", ["a股", "上证", "深证", "沪深", "a-share", "csi", "科创板"], 2.5),
    ("港股", ["港股", "hang seng", "恒生", "hong kong stock", "hsi"], 2.2),
    ("韩股", ["kospi", "kosdaq", "韩股", "samsung electronics", "sk hynix"], 2.0),
    ("日股", ["nikkei", "日股", "topix", "tokyo stock", "boj"], 2.0),
    ("汇率", ["forex", "fx ", "汇率", "usd/cny", "dollar", "yen", "won", "人民币"], 2.2),
    ("黄金", ["gold", "黄金", "xau", "bullion"], 2.0),
    ("原油", ["oil", "crude", "wti", "brent", "原油", "opec"], 2.0),
    ("政策", ["regulation", "regulatory", "sanctions", "tariff", "监管", "制裁", "关税", "证监会", "央行", "sec ", "cftc"], 2.8),
    ("科技", ["semiconductor", "chip", "gpu", "nvidia", "ai ", "artificial intelligence", "半导体", "芯片", "openai"], 2.0),
]

CATEGORY_BASE = {"policy": 1.4, "finance": 1.2, "tech": 1.0}


@dataclass
class Highlight:
    article: Article
    score: float
    why: str
    comment: str = ""
    digest: str = ""

    def to_dict(self) -> dict:
        a = self.article
        return {
            "title": a.title,
            "url": a.url,
            "summary": a.summary,
            "digest": self.digest,
            "source_name": a.source_name,
            "source_home": a.source_home,
            "published_at": _fmt_cn(a.published_at),
            "published_at_iso": a.published_at.isoformat(),
            "category": a.category,
            "category_label": CATEGORY_LABELS.get(a.category, a.category),
            "tags": list(a.tags),
            "score": round(self.score, 2),
            "why": self.why,
            "comment": self.comment,
            "url_hash": a.url_hash,
        }


def score_article(article: Article, now: datetime | None = None) -> tuple[float, str]:
    now = now or datetime.now(timezone.utc)
    blob = f"{article.title}\n{article.summary}\n{' '.join(article.tags)}".lower()
    score = CATEGORY_BASE.get(article.category, 1.0)
    hits: list[str] = []

    for label, kws, weight in THEME_KEYWORDS:
        if any(k in blob for k in kws):
            score += weight
            hits.append(label)

    # Tag overlap bonus
    tag_bonus = {
        "加密": 1.0,
        "美股": 0.8,
        "A股": 0.8,
        "港股": 0.7,
        "韩股": 0.7,
        "日股": 0.7,
        "汇率": 0.7,
        "黄金": 0.6,
        "原油": 0.6,
        "政策": 0.9,
        "科技": 0.5,
    }
    for tag in article.tags:
        if tag in tag_bonus and tag not in hits:
            score += tag_bonus[tag]
            hits.append(tag)
        elif tag in tag_bonus:
            score += tag_bonus[tag] * 0.3

    # Recency: newer within window scores slightly higher
    age_h = max(0.0, (now - article.published_at).total_seconds() / 3600.0)
    score += max(0.0, 1.5 - age_h / 16.0)

    # Prefer items with a real summary
    if article.summary and len(article.summary) > 40:
        score += 0.4

    why = "、".join(hits[:4]) if hits else CATEGORY_LABELS.get(article.category, "综合")
    return score, why


def select_highlights(
    articles: list[Article],
    limit: int = 8,
    now: datetime | None = None,
) -> list[Highlight]:
    """Pick top articles with category diversity (at least one per non-empty category when possible)."""
    if limit <= 0 or not articles:
        return []

    now = now or datetime.now(timezone.utc)
    scored: list[Highlight] = []
    for art in articles:
        s, why = score_article(art, now=now)
        scored.append(Highlight(article=art, score=s, why=why))
    scored.sort(key=lambda h: h.score, reverse=True)

    picked: list[Highlight] = []
    seen_hash: set[str] = set()

    # First pass: best from each category
    for cat in ("finance", "policy", "tech"):
        for h in scored:
            if h.article.category != cat:
                continue
            if h.article.url_hash in seen_hash:
                continue
            picked.append(h)
            seen_hash.add(h.article.url_hash)
            break
        if len(picked) >= limit:
            return picked[:limit]

    # Second pass: fill remaining by score with light theme diversity
    why_counts: dict[str, int] = {}
    for h in picked:
        for part in h.why.split("、"):
            if part:
                why_counts[part] = why_counts.get(part, 0) + 1

    candidates: list[tuple[float, Highlight]] = []
    for h in scored:
        if h.article.url_hash in seen_hash:
            continue
        theme_pen = sum(why_counts.get(part, 0) * 0.5 for part in h.why.split("、") if part)
        candidates.append((h.score - theme_pen, h))
    candidates.sort(key=lambda x: x[0], reverse=True)

    for _, h in candidates:
        if len(picked) >= limit:
            break
        picked.append(h)
        seen_hash.add(h.article.url_hash)
        for part in h.why.split("、"):
            if part:
                why_counts[part] = why_counts.get(part, 0) + 1

    picked.sort(key=lambda h: h.score, reverse=True)
    return picked[:limit]
