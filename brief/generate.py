"""CLI entry: python -m brief generate --hours 24"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from brief import REPORTS_DIR
from brief.classify import load_config
from brief.comment import (
    apply_annotations_by_hash,
    attach_llm_comments,
    comments_payload_template,
    seed_digest_from_summary,
)
from brief.fetch import fetch_all
from brief.render import (
    build_context,
    context_from_report_json,
    default_output_stem,
    load_report_json,
    render_html,
    write_json,
)
from brief.select import select_highlights


def _write_outputs(out_path: Path, context: dict, articles: list) -> tuple[Path, Path]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_html(context)
    out_path.write_text(html, encoding="utf-8")
    json_path = out_path.with_suffix(".json")
    write_json(json_path, context, articles)
    return out_path, json_path


def cmd_generate(args: argparse.Namespace) -> int:
    config = load_config(Path(args.config) if args.config else None)
    articles, results, since, end = fetch_all(config, hours=args.hours)

    highlights = select_highlights(articles, limit=args.picks, now=end)
    seed_digest_from_summary(highlights)
    comment_status = "skipped"
    if args.picks > 0 and not args.no_comments:
        highlights, err = attach_llm_comments(highlights)
        if err == "no_api_key":
            comment_status = "pending_agent"
        elif err:
            comment_status = f"llm_error:{err}"
            print(f"LLM comments failed: {err}", file=sys.stderr)
        else:
            comment_status = "llm_ok"

    context = build_context(articles, results, since, end, highlights=highlights)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = REPORTS_DIR / f"{default_output_stem(end)}.html"

    out_path, json_path = _write_outputs(out_path, context, articles)

    print(f"Report: {out_path.resolve()}")
    print(f"JSON:   {json_path.resolve()}")
    print(
        f"Items:  {len(articles)} "
        f"(window {context['window_start']} → {context['window_end']} {context['timezone_label']})"
    )
    for section in context["sections"]:
        print(f"  - {section['label']}: {section['count']}")
    print(f"Picks:  {len(highlights)} (comments: {comment_status})")
    for i, h in enumerate(highlights, 1):
        flag = "✓" if h.comment else "·"
        print(f"  {flag} {i}. [{h.why}] {h.article.title[:70]}")

    if comment_status == "pending_agent":
        print("Comments pending: set BRIEF_LLM_API_KEY/OPENAI_API_KEY, or agent-fill via `comment`/`render`.")

    failed = [r for r in results if not r.ok]
    if failed:
        print(f"Source errors: {len(failed)}")
        for r in failed:
            print(f"  ! {r.source_name}: {r.error}")

    if not results:
        print("No sources configured.", file=sys.stderr)
        return 1
    if all(not r.ok for r in results):
        print("All sources failed.", file=sys.stderr)
        return 1
    return 0


def cmd_comment(args: argparse.Namespace) -> int:
    """Fill highlight comments via LLM or print a template for the agent."""
    json_path = Path(args.json)
    payload = load_report_json(json_path)
    highlights = payload.get("highlights") or []
    if not highlights:
        print("No highlights in JSON.", file=sys.stderr)
        return 1

    if args.template:
        print(comments_payload_template(highlights))
        return 0

    if args.from_file:
        data = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
        mapping: dict[str, dict[str, str]] = {}
        for item in data:
            key = item.get("url_hash") or item.get("url")
            if not key:
                continue
            mapping[key] = {
                "digest": (item.get("digest") or "").strip(),
                "comment": (item.get("comment") or "").strip(),
            }
        n = apply_annotations_by_hash(highlights, mapping)
        payload["highlights"] = highlights
        payload.setdefault("meta", {})["highlights_commented"] = sum(
            1 for h in highlights if (h.get("comment") or "").strip()
        )
        payload.setdefault("meta", {})["highlights_digested"] = sum(
            1 for h in highlights if (h.get("digest") or h.get("summary") or "").strip()
        )
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Applied {n} annotations → {json_path.resolve()}")
        return 0
    # Rebuild Highlight-like flow via LLM using dicts → temporary objects
    from brief.fetch import Article
    from brief.select import Highlight
    from datetime import datetime

    objs: list[Highlight] = []
    for h in highlights:
        published = h.get("published_at_iso") or datetime.now().isoformat()
        try:
            published_at = datetime.fromisoformat(published)
        except ValueError:
            published_at = datetime.now().astimezone()
        art = Article(
            title=h.get("title") or "",
            url=h.get("url") or "",
            summary=h.get("summary") or "",
            source_id="",
            source_name=h.get("source_name") or "",
            published_at=published_at,
            category=h.get("category") or "finance",
            tags=list(h.get("tags") or []),
            url_hash=h.get("url_hash") or "",
            source_home=h.get("source_home") or "",
        )
        objs.append(Highlight(article=art, score=float(h.get("score") or 0), why=h.get("why") or "", comment=h.get("comment") or "", digest=h.get("digest") or ""))

    objs, err = attach_llm_comments(objs)
    if err == "no_api_key":
        print("No LLM API key. Use --template and --from-file, or set BRIEF_LLM_API_KEY.", file=sys.stderr)
        print(comments_payload_template(highlights))
        return 2
    if err:
        print(f"LLM failed: {err}", file=sys.stderr)
        return 1

    for dest, src in zip(highlights, objs):
        dest["comment"] = src.comment
        if src.digest:
            dest["digest"] = src.digest
    payload["highlights"] = highlights
    payload.setdefault("meta", {})["highlights_commented"] = sum(
        1 for h in highlights if (h.get("comment") or "").strip()
    )
    payload.setdefault("meta", {})["highlights_digested"] = sum(
        1 for h in highlights if (h.get("digest") or h.get("summary") or "").strip()
    )
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"LLM digests/comments written → {json_path.resolve()}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    """Re-render HTML from an existing report JSON (after comments filled)."""
    json_path = Path(args.json)
    payload = load_report_json(json_path)
    context = context_from_report_json(payload)
    out_path = Path(args.out) if args.out else json_path.with_suffix(".html")
    out_path.write_text(render_html(context), encoding="utf-8")
    # Keep JSON meta in sync
    payload.setdefault("meta", {})["highlights_commented"] = context["highlights_commented"]
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {out_path.resolve()}")
    print(f"Highlights with comments: {context['highlights_commented']}/{len(context['highlights'])}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成近 N 小时财经科技 HTML 日报")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="拉取 RSS、精选并生成 HTML 报告")
    gen.add_argument("--hours", type=float, default=24.0, help="时间窗口（小时），默认 24")
    gen.add_argument("--picks", type=int, default=8, help="精选短评条数，默认 8；0 关闭")
    gen.add_argument("--no-comments", action="store_true", help="只精选不写短评")
    gen.add_argument("--out", type=str, default=None, help="输出 HTML 路径")
    gen.add_argument("--config", type=str, default=None, help="sources.yaml 路径")
    gen.set_defaults(func=cmd_generate)

    cmt = sub.add_parser("comment", help="为 JSON 中的精选条目生成/写入短评")
    cmt.add_argument("--json", type=str, required=True, help="报告 JSON 路径")
    cmt.add_argument("--template", action="store_true", help="打印待填短评 JSON 模板")
    cmt.add_argument("--from-file", type=str, default=None, help="从已填短评 JSON 写回")
    cmt.set_defaults(func=cmd_comment)

    rnd = sub.add_parser("render", help="从 JSON 重新渲染 HTML")
    rnd.add_argument("--json", type=str, required=True, help="报告 JSON 路径")
    rnd.add_argument("--out", type=str, default=None, help="输出 HTML 路径")
    rnd.set_defaults(func=cmd_render)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
