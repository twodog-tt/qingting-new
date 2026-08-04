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

## GitHub Pages 部署（推荐：本地定时 → 推送 → Pages）

流程：本机每天 12:00 生成带 LLM 短评的日报 → 提交 `site/` → push → Actions 仅负责把 `site/` 部署到 Pages。

### 1. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入 BRIEF_LLM_API_KEY
```

### 2. 安装本地定时任务（macOS launchd）

```bash
bash scripts/install_launchd.sh
```

- 每天 **12:00**（系统时区，你当前为 CST）自动跑 `scripts/daily_publish.sh`
- 日志在 `logs/`
- 卸载：`bash scripts/uninstall_launchd.sh`

也可手动跑一次：

```bash
bash scripts/daily_publish.sh
```

### 3. GitHub 设置

1. **Settings → Pages → Source**：选 **GitHub Actions**
2. 不再需要把 LLM Key 放进 GitHub Secrets（Key 只留在本地 `.env`）

> 注意：到点时 Mac 需开机且未深度休眠；若经常关机，可改回云端 Actions 定时。

### 备选：云端定时

若改用 GitHub Actions 定时生成，需在 Secrets 配置 `BRIEF_LLM_API_KEY`，并把 workflow 改回 `schedule`（见仓库历史）。当前默认是 **push `site/` 后部署**。

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
