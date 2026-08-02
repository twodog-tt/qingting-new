"""Fetch RSS feeds, filter by time window, and dedupe."""

from __future__ import annotations

import calendar
import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import feedparser
import httpx

from brief.classify import BriefConfig, Source, classify_article, topic_labels

USER_AGENT = (
    "QingtingDailyBrief/1.0 (+https://github.com/local/qingting-new; research brief)"
)
TIMEOUT = 25.0


@dataclass
class Article:
    title: str
    url: str
    summary: str
    source_id: str
    source_name: str
    published_at: datetime
    category: str
    tags: list[str] = field(default_factory=list)
    url_hash: str = ""
    source_home: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["published_at"] = self.published_at.isoformat()
        return data


@dataclass
class SourceResult:
    source_id: str
    source_name: str
    ok: bool
    fetched: int = 0
    kept: int = 0
    error: str | None = None
    source_home: str = ""
    feed_url: str = ""

def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    # Drop common tracking params
    drop = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
    query = parse_qs(parsed.query, keep_blank_values=False)
    cleaned = {k: v for k, v in query.items() if k.lower() not in drop}
    new_query = urlencode(cleaned, doseq=True)
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", new_query, ""))


def _url_hash(url: str) -> str:
    return hashlib.sha256(_normalize_url(url).encode("utf-8")).hexdigest()[:32]


def _title_key(title: str) -> str:
    t = re.sub(r"[^\w\u4e00-\u9fff]+", "", (title or "").lower())
    return t[:80]


def _parse_entry_time(entry: dict[str, Any]) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
            except (OverflowError, ValueError, OSError):
                pass
    for key in ("published", "updated"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (TypeError, ValueError, IndexError):
            continue
    return None


def _entry_link(entry: dict[str, Any]) -> str:
    link = entry.get("link") or ""
    if link:
        return link
    links = entry.get("links") or []
    for item in links:
        href = item.get("href")
        if href:
            return href
    return ""


def _entry_summary(entry: dict[str, Any]) -> str:
    summary = entry.get("summary") or entry.get("description") or ""
    if not summary and entry.get("content"):
        parts = entry["content"]
        if parts and isinstance(parts, list):
            summary = parts[0].get("value") or ""
    text = _strip_html(summary)
    if len(text) > 280:
        text = text[:277].rstrip() + "…"
    return text


def fetch_source(
    client: httpx.Client,
    source: Source,
    since: datetime,
    config: BriefConfig,
) -> tuple[list[Article], SourceResult]:
    try:
        resp = client.get(source.url)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as exc:  # noqa: BLE001 — surface per-source errors in report
        return [], SourceResult(
            source_id=source.id,
            source_name=source.name,
            ok=False,
            error=str(exc),
            source_home=source.home_url,
            feed_url=source.url,
        )

    articles: list[Article] = []
    for entry in parsed.entries or []:
        published = _parse_entry_time(entry)
        if published is None:
            continue
        if published < since:
            continue
        title = _strip_html(entry.get("title") or "").strip()
        url = _entry_link(entry)
        if not title or not url:
            continue
        summary = _entry_summary(entry)
        category = classify_article(title, summary, source.default_category, config)
        tags = topic_labels(source.region_tags, title, summary, config)
        articles.append(
            Article(
                title=title,
                url=url,
                summary=summary,
                source_id=source.id,
                source_name=source.name,
                published_at=published,
                category=category,
                tags=tags,
                url_hash=_url_hash(url),
                source_home=source.home_url,
            )
        )

    return articles, SourceResult(
        source_id=source.id,
        source_name=source.name,
        ok=True,
        fetched=len(parsed.entries or []),
        kept=len(articles),
        source_home=source.home_url,
        feed_url=source.url,
    )


def dedupe(articles: list[Article]) -> list[Article]:
    by_url: dict[str, Article] = {}
    by_title: dict[str, Article] = {}
    ordered: list[Article] = []

    for art in sorted(articles, key=lambda a: a.published_at, reverse=True):
        if art.url_hash in by_url:
            continue
        tkey = _title_key(art.title)
        if tkey and tkey in by_title:
            continue
        by_url[art.url_hash] = art
        if tkey:
            by_title[tkey] = art
        ordered.append(art)
    return ordered


def fetch_all(
    config: BriefConfig,
    hours: float = 24.0,
    now: datetime | None = None,
) -> tuple[list[Article], list[SourceResult], datetime, datetime]:
    end = now or datetime.now(timezone.utc)
    since = end - timedelta(hours=hours)
    enabled = [s for s in config.sources if s.enabled]

    all_articles: list[Article] = []
    results: list[SourceResult] = []

    with httpx.Client(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"},
    ) as client:
        for source in enabled:
            arts, result = fetch_source(client, source, since, config)
            all_articles.extend(arts)
            results.append(result)

    return dedupe(all_articles), results, since, end
