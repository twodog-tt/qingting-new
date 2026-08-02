"""Render Chinese HTML daily brief and optional JSON sidecar."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from brief import CATEGORIES, CATEGORY_LABELS, TEMPLATE_DIR
from brief.fetch import Article, SourceResult
from brief.select import Highlight

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _fmt_cn(dt: datetime) -> str:
    local = dt.astimezone(TZ_SHANGHAI)
    return local.strftime("%Y-%m-%d %H:%M")


def group_by_category(articles: list[Article]) -> dict[str, list[Article]]:
    grouped: dict[str, list[Article]] = {c: [] for c in CATEGORIES}
    for art in articles:
        cat = art.category if art.category in grouped else "finance"
        grouped[cat].append(art)
    for cat in grouped:
        grouped[cat].sort(key=lambda a: a.published_at, reverse=True)
    return grouped


def highlights_to_context(highlights: list[Highlight] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for h in highlights:
        if isinstance(h, Highlight):
            out.append(h.to_dict())
        else:
            out.append(h)
    return out


def build_context(
    articles: list[Article],
    source_results: list[SourceResult],
    since: datetime,
    end: datetime,
    generated_at: datetime | None = None,
    supplements: list[dict[str, Any]] | None = None,
    highlights: list[Highlight] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    generated = generated_at or datetime.now(timezone.utc)
    grouped = group_by_category(articles)
    sections = []
    for cat in CATEGORIES:
        items = grouped[cat]
        sections.append(
            {
                "id": cat,
                "label": CATEGORY_LABELS[cat],
                "count": len(items),
                "articles": [
                    {
                        "title": a.title,
                        "url": a.url,
                        "summary": a.summary,
                        "source_name": a.source_name,
                        "source_home": a.source_home,
                        "published_at": _fmt_cn(a.published_at),
                        "tags": a.tags,
                    }
                    for a in items
                ],
            }
        )

    failed = [r for r in source_results if not r.ok]
    ok_count = sum(1 for r in source_results if r.ok)
    highlight_items = highlights_to_context(highlights or [])
    commented = sum(1 for h in highlight_items if (h.get("comment") or "").strip())

    # Unique sources for footer directory
    source_dir: dict[str, dict[str, str]] = {}
    for r in source_results:
        if r.source_name and r.source_name not in source_dir:
            source_dir[r.source_name] = {
                "name": r.source_name,
                "home": r.source_home or "",
                "feed_url": r.feed_url or "",
            }
    for art in articles:
        if art.source_name and art.source_name not in source_dir:
            source_dir[art.source_name] = {
                "name": art.source_name,
                "home": art.source_home or "",
                "feed_url": "",
            }

    return {
        "title": "财经科技日报",
        "report_date": end.astimezone(TZ_SHANGHAI).strftime("%Y-%m-%d"),
        "window_start": _fmt_cn(since),
        "window_end": _fmt_cn(end),
        "generated_at": _fmt_cn(generated),
        "timezone_label": "UTC+8",
        "total_count": len(articles),
        "sections": sections,
        "highlights": highlight_items,
        "highlights_commented": commented,
        "supplements": supplements or [],
        "sources_ok": ok_count,
        "sources_total": len(source_results),
        "source_errors": [
            {"name": r.source_name, "error": r.error or "unknown"} for r in failed
        ],
        "source_stats": [
            {
                "name": r.source_name,
                "ok": r.ok,
                "fetched": r.fetched,
                "kept": r.kept,
                "error": r.error,
                "home": r.source_home,
                "feed_url": r.feed_url,
            }
            for r in source_results
        ],
        "source_directory": sorted(source_dir.values(), key=lambda s: s["name"].lower()),
    }


def render_html(context: dict[str, Any], template_dir: Path | None = None) -> str:
    env = Environment(
        loader=FileSystemLoader(str(template_dir or TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("report.html")
    return template.render(**context)


def write_json(path: Path, context: dict[str, Any], articles: list[Article]) -> None:
    payload = {
        "meta": {
            "report_date": context["report_date"],
            "window_start": context["window_start"],
            "window_end": context["window_end"],
            "generated_at": context["generated_at"],
            "total_count": context["total_count"],
            "highlights_commented": context.get("highlights_commented", 0),
        },
        "highlights": context.get("highlights") or [],
        "sections": context["sections"],
        "supplements": context["supplements"],
        "source_stats": context["source_stats"],
        "source_errors": context.get("source_errors") or [],
        "source_directory": context.get("source_directory") or [],
        "articles": [a.to_dict() for a in articles],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_report_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def context_from_report_json(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("meta") or {}
    highlights = payload.get("highlights") or []
    commented = sum(1 for h in highlights if (h.get("comment") or "").strip())
    return {
        "title": "财经科技日报",
        "report_date": meta.get("report_date", ""),
        "window_start": meta.get("window_start", ""),
        "window_end": meta.get("window_end", ""),
        "generated_at": meta.get("generated_at", ""),
        "timezone_label": "UTC+8",
        "total_count": meta.get("total_count", 0),
        "sections": payload.get("sections") or [],
        "highlights": highlights,
        "highlights_commented": commented,
        "supplements": payload.get("supplements") or [],
        "sources_ok": sum(1 for s in (payload.get("source_stats") or []) if s.get("ok")),
        "sources_total": len(payload.get("source_stats") or []),
        "source_errors": payload.get("source_errors")
        or [
            {"name": s.get("name"), "error": s.get("error")}
            for s in (payload.get("source_stats") or [])
            if not s.get("ok") and s.get("error")
        ],
        "source_stats": payload.get("source_stats") or [],
        "source_directory": payload.get("source_directory")
        or [
            {
                "name": s.get("name"),
                "home": s.get("home") or "",
                "feed_url": s.get("feed_url") or "",
            }
            for s in (payload.get("source_stats") or [])
            if s.get("name")
        ],
    }


def default_output_stem(end: datetime) -> str:
    local = end.astimezone(TZ_SHANGHAI)
    return local.strftime("%Y-%m-%d_%H%M")
