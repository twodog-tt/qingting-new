# Qingting Daily Brief

按需生成**近 24 小时**科技 / 金融 / 政策 HTML 日报。覆盖加密货币、美股、A 股、港股、韩股、日股、汇率、黄金、原油及相关政策。

## 快速开始

```bash
cd qingting-new
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m brief generate --hours 24 --picks 8
```

生成后终端会打印路径，例如：

```text
Report: .../reports/2026-08-02_1448.html
JSON:   .../reports/2026-08-02_1448.json
Picks:  8 (comments: pending_agent)
```

用浏览器打开该 HTML 即可。macOS 可执行：

```bash
open reports/<生成的文件名>.html
```

### 精选短评

报告会按主题相关性自动精选约 8 条「今日精选短评」。

- **有 API Key**：设置 `BRIEF_LLM_API_KEY` 或 `OPENAI_API_KEY` 后，生成时自动写短评。
- **无 API Key（Cursor Agent）**：Agent 为精选条目写短评后执行：

```bash
python -m brief comment --json reports/<file>.json --from-file reports/_comments.json
python -m brief render --json reports/<file>.json
```

### 常用参数

```bash
python -m brief generate --hours 24 --picks 8
python -m brief generate --hours 12 --picks 5 --out reports/custom.html
python -m brief generate --picks 0          # 关闭精选
python -m brief generate --no-comments      # 只精选不写短评
python -m brief comment --json reports/x.json
python -m brief render --json reports/x.json
```

## 报告结构

1. **今日精选短评**：相关性最高的条目 + **概括**（新闻主体）+ **短评**（影响解读）  
2. **科技 / 金融 / 政策**：完整列表  

每条含标题链接、来源、发布时间（UTC+8）、摘要与主题标签。

## 添加 / 调整新闻源

编辑 [`config/sources.yaml`](config/sources.yaml)：

```yaml
- id: example
  name: Example Feed
  url: https://example.com/rss
  default_category: finance   # tech | finance | policy
  region_tags: [us, crypto]   # crypto us cn hk kr jp fx gold oil policy tech
  enabled: true
```

`classification` 下的关键词用于覆盖源默认分类。

## 在 Cursor 里怎么用

直接说「帮我出今日报告」或「近 24 小时新闻」。项目内 Skill [`.cursor/skills/daily-brief/SKILL.md`](.cursor/skills/daily-brief/SKILL.md) 约定了生成、打开与补检索流程。

## 目录

```text
config/sources.yaml   # RSS 与分类规则
brief/                # CLI 与管线
templates/report.html # 报告模板
reports/              # 生成的 HTML / JSON（默认 gitignore）
```
