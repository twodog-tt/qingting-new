---
name: daily-brief
description: >-
  Generate the near-24h Chinese tech/finance/policy HTML daily brief for this
  repo. Use when the user asks for 今日报告, 近24小时新闻, 出份日报, daily brief,
  or similar market news summaries covering crypto, equities, FX, gold, oil, and
  related policy. Includes selecting top highlights and writing short comments.
---

# Daily Brief（近 24 小时财经科技日报）

## When to use

User asks for something like:

- 今日报告 / 出份日报 / 近 24 小时新闻
- daily brief / last 24 hours market news

## Steps

1. From the repo root (`qingting-new`), ensure deps exist, then generate:

```bash
source .venv/bin/activate   # or: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python -m brief generate --hours 24 --picks 8
```

2. Note the printed HTML/JSON paths under `reports/`.

3. **Fill 概括 + 短评** (required unless LLM already wrote them):

- If generate printed `comments: llm_ok`, skip to step 4.
- If `comments: pending_agent` (no API key), you **must** write both fields for each highlight:
  1. Read `highlights` from the report JSON.
  2. For each item write:
     - `digest`（内容概括）：2–4 句中文，客观复述新闻主体（发生了什么、涉及谁、关键数据/结论），让用户不点链接也能看懂；不编造未给出的事实。
     - `comment`（短评）：2–4 句，为何重要、可能影响哪些资产/板块；无买卖建议。
  3. Write `reports/_comments.json` as a list of `{ "url_hash": "...", "digest": "...", "comment": "..." }`.
  4. Apply and re-render:

```bash
python -m brief comment --json reports/<file>.json --from-file reports/_comments.json
python -m brief render --json reports/<file>.json
```

Optional unattended LLM (OpenAI-compatible):

```bash
export BRIEF_LLM_API_KEY=...   # or OPENAI_API_KEY
export BRIEF_LLM_MODEL=gpt-4o-mini   # optional
python -m brief generate --hours 24 --picks 8
# or later: python -m brief comment --json reports/<file>.json
```

4. Open the HTML for the user and give the **absolute path**.

5. Coverage check: if tech/finance/policy or Asia markets look thin, web-search 3–5 supplements; do not invent URLs.

6. Chat reply: very short — mention how many highlights got comments + 2–3 takeaways; full content is the HTML.

## Scope

- Categories: 科技 / 金融 / 政策
- Themes: 加密货币、美股、A股、港股、韩股、日股、汇率、黄金、原油及相关政策
- Highlights: default top 8 with short comments (not every article)
- No long essay / writing pipeline

## Failure handling

- Non-zero exit (all sources failed): fix network/deps once, retry.
- Per-source errors in CLI/HTML footer are OK.
