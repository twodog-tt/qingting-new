"""Publish daily brief to a static site/ tree for GitHub Pages."""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from brief import ROOT, TEMPLATE_DIR
from brief.classify import load_config
from brief.comment import attach_llm_comments, seed_digest_from_summary
from brief.fetch import fetch_all
from brief.render import build_context, default_output_stem, render_html, write_json
from brief.select import select_highlights

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")


def _inject_site_nav(html: str, report_date: str) -> str:
    """Insert a small site nav after <body> for Pages browsing."""
    nav = f"""
  <nav class="site-nav" aria-label="站点导航">
    <a href="./index.html">今日日报</a>
    <span class="sep">·</span>
    <a href="./archive/index.html">近7日归档</a>
    <span class="sep">·</span>
    <span class="nav-date">{report_date}</span>
  </nav>
"""
    # archive copies live one level deeper
    if "<!-- site-nav -->" in html:
        return html
    style = """
  <style>
    .site-nav {
      max-width: 880px;
      margin: 0 auto;
      padding: 0.85rem 1.25rem 0;
      font-size: 0.9rem;
      color: #5c6670;
    }
    .site-nav a { color: #1d4e89; text-decoration: none; font-weight: 560; }
    .site-nav a:hover { text-decoration: underline; }
    .site-nav .sep { margin: 0 0.35rem; color: #c4b8a8; }
    .site-nav .nav-date { color: #1a1f24; font-weight: 600; }
  </style>
  <!-- site-nav -->
"""
    if "</head>" in html:
        html = html.replace("</head>", style + "</head>", 1)
    if "<body>" in html:
        html = html.replace("<body>", "<body>" + nav, 1)
    return html


def _inject_archive_nav(html: str, report_date: str) -> str:
    nav = f"""
  <nav class="site-nav" aria-label="站点导航">
    <a href="../index.html">今日日报</a>
    <span class="sep">·</span>
    <a href="./index.html">近7日归档</a>
    <span class="sep">·</span>
    <span class="nav-date">{report_date}</span>
  </nav>
"""
    style = """
  <style>
    .site-nav {
      max-width: 880px;
      margin: 0 auto;
      padding: 0.85rem 1.25rem 0;
      font-size: 0.9rem;
      color: #5c6670;
    }
    .site-nav a { color: #1d4e89; text-decoration: none; font-weight: 560; }
    .site-nav a:hover { text-decoration: underline; }
    .site-nav .sep { margin: 0 0.35rem; color: #c4b8a8; }
    .site-nav .nav-date { color: #1a1f24; font-weight: 600; }
  </style>
  <!-- site-nav -->
"""
    if "<!-- site-nav -->" in html:
        # replace existing nav block roughly by rewriting paths for archive depth
        html = re.sub(
            r"<nav class=\"site-nav\"[\s\S]*?</nav>",
            nav.strip(),
            html,
            count=1,
        )
        return html
    if "</head>" in html:
        html = html.replace("</head>", style + "</head>", 1)
    if "<body>" in html:
        html = html.replace("<body>", "<body>" + nav, 1)
    return html


def list_archive_dates(archive_dir: Path) -> list[str]:
    dates: list[str] = []
    if not archive_dir.is_dir():
        return dates
    for path in archive_dir.glob("*.html"):
        m = DATE_RE.match(path.name)
        if m:
            dates.append(m.group(1))
    return sorted(dates, reverse=True)


def prune_archives(archive_dir: Path, keep_days: int, today: str) -> list[str]:
    """Keep only dates within [today-(keep_days-1), today]. Returns removed filenames."""
    if keep_days <= 0:
        return []
    today_dt = datetime.strptime(today, "%Y-%m-%d").date()
    cutoff = today_dt - timedelta(days=keep_days - 1)
    removed: list[str] = []
    for path in sorted(archive_dir.glob("*.html")):
        m = DATE_RE.match(path.name)
        if not m:
            continue
        d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        if d < cutoff or d > today_dt:
            path.unlink(missing_ok=True)
            removed.append(path.name)
    return removed


def write_archive_index(archive_dir: Path, dates: list[str], latest_date: str) -> Path:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("archive_index.html")
    html = template.render(dates=dates, latest_date=latest_date, count=len(dates))
    out = archive_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    return out


def publish_site(
    *,
    site_dir: Path,
    hours: float = 24.0,
    picks: int = 8,
    keep_days: int = 7,
    require_llm: bool = True,
    config_path: Path | None = None,
) -> int:
    config = load_config(config_path)
    articles, results, since, end = fetch_all(config, hours=hours)

    if not results or all(not r.ok for r in results):
        print("All sources failed or none configured.", file=sys.stderr)
        return 1

    highlights = select_highlights(articles, limit=picks, now=end)
    seed_digest_from_summary(highlights)

    if picks > 0:
        highlights, err = attach_llm_comments(highlights)
        if require_llm:
            if err == "no_api_key":
                print(
                    "LLM API key required for Pages publish. "
                    "Set BRIEF_LLM_API_KEY or OPENAI_API_KEY.",
                    file=sys.stderr,
                )
                return 2
            if err:
                print(f"LLM comments failed: {err}", file=sys.stderr)
                return 2
            missing_comments = [h for h in highlights if not h.comment.strip()]
            if missing_comments:
                print(f"LLM returned empty comments for {len(missing_comments)} picks.", file=sys.stderr)
                return 2
            for h in highlights:
                if not h.digest.strip():
                    h.digest = h.article.summary or h.article.title

    context = build_context(articles, results, since, end, highlights=highlights)
    report_date = context["report_date"]
    html = render_html(context)
    html_home = _inject_site_nav(html, report_date)
    html_arch = _inject_archive_nav(html, report_date)

    site_dir = site_dir.resolve()
    archive_dir = site_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    index_path = site_dir / "index.html"
    archive_path = archive_dir / f"{report_date}.html"
    index_path.write_text(html_home, encoding="utf-8")
    archive_path.write_text(html_arch, encoding="utf-8")

    # Also keep a machine-readable copy under site/data for debugging (optional small json)
    data_dir = site_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    write_json(data_dir / f"{report_date}.json", context, articles)

    removed = prune_archives(archive_dir, keep_days=keep_days, today=report_date)
    dates = list_archive_dates(archive_dir)
    write_archive_index(archive_dir, dates, latest_date=report_date)

    # Local reports mirror for developers
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stem = default_output_stem(end)
    (reports_dir / f"{stem}.html").write_text(html, encoding="utf-8")
    write_json(reports_dir / f"{stem}.json", context, articles)

    print(f"Site index:   {index_path}")
    print(f"Site archive: {archive_path}")
    print(f"Archive days: {len(dates)} (keep_days={keep_days})")
    if removed:
        print(f"Pruned:       {', '.join(removed)}")
    print(f"Items:        {len(articles)}; picks={len(highlights)}")
    failed = [r for r in results if not r.ok]
    if failed:
        print(f"Source errors: {len(failed)}")
        for r in failed:
            print(f"  ! {r.source_name}: {r.error}")
    return 0
