# Qingting Daily Brief

开源的**近 24 小时**科技 / 金融 / 政策 HTML 日报。覆盖加密货币、美股、A 股、港股、韩股、日股、汇率、黄金、原油及相关政策。

- 本地一键生成 HTML
- GitHub Actions 每天 **北京时间 10:00** 自动更新
- GitHub Pages 发布首页 + **近 7 日归档**
- 精选条目默认生成 LLM「概括 + 短评」

> 内容来自公开 RSS，仅供信息聚合；不构成投资建议。

## 在线站点

仓库启用 GitHub Pages（Source = **GitHub Actions**）后，地址一般为：

`https://<user>.github.io/qingting-new/`

## 快速开始（本地）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 本地预览（可无 LLM）
python -m brief generate --hours 24 --picks 8

# 发布到 site/（默认要求 LLM Key，与 Pages 一致）
export BRIEF_LLM_API_KEY=sk-...   # 或 OPENAI_API_KEY
python -m brief publish --hours 24 --picks 8 --keep-days 7
```

## GitHub Pages 部署

### 1. 仓库设置

1. **Settings → Pages → Build and deployment → Source**：选 **GitHub Actions**
2. **Settings → Secrets and variables → Actions** 添加：

| Secret | 必填 | 说明 |
|--------|------|------|
| `BRIEF_LLM_API_KEY` 或 `OPENAI_API_KEY` | 是 | OpenAI 兼容接口的 API Key（Pages 默认要有短评） |
| `BRIEF_LLM_BASE_URL` / `OPENAI_BASE_URL` | 否 | 自定义兼容网关，默认 `https://api.openai.com/v1` |
| `BRIEF_LLM_MODEL` / `OPENAI_MODEL` | 否 | 默认 `gpt-4o-mini` |

### 2. 工作流

[`.github/workflows/daily-brief.yml`](.github/workflows/daily-brief.yml)：

- 定时：`cron: "0 2 * * *"`（UTC）= 北京时间每天 10:00
- 也可在 Actions 里手动 **Run workflow**
- 产出写入 `site/`（`index.html` + `archive/YYYY-MM-DD.html`），超过 7 天自动删
- 将 `site/` 提交回仓库以便保留近 7 日归档，并部署到 Pages

### 3. 本地等价命令

```bash
python -m brief publish --hours 24 --picks 8 --keep-days 7 --site site
```

## 报告结构

1. **今日精选短评**：概括（新闻主体）+ 短评（影响解读）
2. **科技 / 金融 / 政策**：完整列表（含来源与原文链接）

## 添加新闻源

编辑 [`config/sources.yaml`](config/sources.yaml)：

```yaml
- id: example
  name: Example Feed
  url: https://example.com/rss
  default_category: finance   # tech | finance | policy
  region_tags: [us, crypto]
  enabled: true
```

## 常用 CLI

```bash
python -m brief generate --hours 24 --picks 8
python -m brief publish --hours 24 --picks 8 --keep-days 7
python -m brief comment --json reports/x.json
python -m brief render --json reports/x.json
```

## 目录

```text
config/sources.yaml              # RSS 与分类规则
brief/                           # CLI 与管线
templates/                       # HTML 模板
site/                            # GitHub Pages 站点（近 7 日归档会提交）
reports/                         # 本地生成物（gitignore）
.github/workflows/daily-brief.yml
```

## License

[MIT](LICENSE)
