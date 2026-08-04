"""Generate digests and short Chinese commentaries for highlight articles."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from brief.select import Highlight

SYSTEM_PROMPT = """你是面向投资者的中文财经科技简报编辑。
针对给定新闻，输出 JSON 对象（不要 Markdown 代码块），字段：
{
  "digest": "内容概括",
  "comment": "短评"
}

「digest」要求：
1. 中文，2–4 句，客观复述新闻主体：发生了什么、涉及谁、关键数据/结论
2. 不跳转原文也能看懂；不编造标题与摘要未给出的事实
3. 若原文摘要不足，仅基于标题做谨慎概括，并避免断言细节

「comment」要求：
1. 中文，2–4 句，约 80–150 字
2. 说明为何重要、可能影响哪些资产或板块
3. 不编造事实；不确定写「需观察」；不要买卖建议
"""


def _llm_settings() -> tuple[str, str, str] | None:
    """Return (api_key, base_url, model) or None if not configured."""
    key = (
        os.environ.get("BRIEF_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
    )
    if not key:
        return None
    base = (
        os.environ.get("BRIEF_LLM_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    model = os.environ.get("BRIEF_LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
    if os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("BRIEF_LLM_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        if "anthropic" not in base:
            return None
    return key, base, model


def _parse_llm_json(content: str) -> dict[str, str]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return {
                "digest": str(data.get("digest") or "").strip(),
                "comment": str(data.get("comment") or "").strip(),
            }
    except json.JSONDecodeError:
        pass
    # Fallback: treat whole reply as comment
    cleaned = re.sub(r"\s+", " ", text).strip()
    return {"digest": "", "comment": cleaned}


def generate_comment_llm(
    highlight: Highlight,
    client: httpx.Client,
    key: str,
    base: str,
    model: str,
    retries: int = 4,
) -> dict[str, str]:
    import time

    user = (
        f"分类：{highlight.article.category}\n"
        f"相关主题：{highlight.why}\n"
        f"标题：{highlight.article.title}\n"
        f"来源：{highlight.article.source_name}\n"
        f"摘要：{highlight.article.summary or '（无摘要）'}\n"
    )
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "temperature": 0.4,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=60.0,
            )
            if resp.status_code in {429, 500, 502, 503, 504}:
                wait = 2 ** attempt
                print(
                    f"LLM HTTP {resp.status_code}, retry {attempt + 1}/{retries} in {wait}s…",
                    flush=True,
                )
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            return _parse_llm_json(content)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            wait = 2 ** attempt
            print(f"LLM network error ({exc}), retry {attempt + 1}/{retries} in {wait}s…", flush=True)
            time.sleep(wait)
    if last_exc:
        raise last_exc
    raise httpx.HTTPStatusError(
        "LLM unavailable after retries",
        request=httpx.Request("POST", f"{base}/chat/completions"),
        response=httpx.Response(503),
    )


def attach_llm_comments(highlights: list[Highlight]) -> tuple[list[Highlight], str | None]:
    """Fill highlight.digest + comment via OpenAI-compatible API."""
    settings = _llm_settings()
    if not settings:
        return highlights, "no_api_key"
    key, base, model = settings
    try:
        with httpx.Client(timeout=60.0) as client:
            for h in highlights:
                result = generate_comment_llm(h, client, key, base, model)
                if result.get("digest"):
                    h.digest = result["digest"]
                elif h.article.summary and not h.digest:
                    h.digest = h.article.summary
                if result.get("comment"):
                    h.comment = result["comment"]
    except Exception as exc:  # noqa: BLE001
        return highlights, str(exc)
    return highlights, None


def apply_annotations_by_hash(
    highlights: list[dict[str, Any]],
    annotations: dict[str, dict[str, str]],
) -> int:
    """Apply url_hash -> {digest, comment} onto highlight dicts. Returns count touched."""
    n = 0
    for h in highlights:
        key = h.get("url_hash") or h.get("url")
        if not key or key not in annotations:
            continue
        item = annotations[key]
        changed = False
        if item.get("digest"):
            h["digest"] = item["digest"].strip()
            changed = True
        if item.get("comment"):
            h["comment"] = item["comment"].strip()
            changed = True
        if changed:
            n += 1
    return n


# Back-compat alias
def apply_comments_by_hash(highlights: list[dict[str, Any]], comments: dict[str, str]) -> int:
    annotations = {k: {"comment": v} for k, v in comments.items()}
    return apply_annotations_by_hash(highlights, annotations)


def comments_payload_template(highlights: list[dict[str, Any]]) -> str:
    """JSON template for agent/LLM to fill digest + comment."""
    items = [
        {
            "url_hash": h.get("url_hash"),
            "title": h.get("title"),
            "why": h.get("why"),
            "summary": h.get("summary") or "",
            "digest": h.get("digest") or "",
            "comment": h.get("comment") or "",
        }
        for h in highlights
    ]
    return json.dumps(items, ensure_ascii=False, indent=2)


def seed_digest_from_summary(highlights: list[Highlight]) -> None:
    """If digest empty but RSS summary exists, use summary as provisional digest."""
    for h in highlights:
        if not h.digest and h.article.summary:
            h.digest = h.article.summary
