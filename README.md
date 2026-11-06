# 📡 FeedFlow AI

> *I was spending 45 minutes every morning reading Hacker News, Reddit, and various tech blogs just to figure out what was worth reading. So I built this.*

A personal AI-powered news briefing pipeline that fetches stories from the sources I actually care about, scores them by relevance to my interests, summarizes the good ones, and delivers a clean daily briefing â€” automatically, every morning.

Built over **30 days, 1 hour/day** as a personal project to actually ship something end-to-end with real AI tooling.

![CI](https://github.com/Harshads-git/feedflow-ai/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Version](https://img.shields.io/badge/version-1.0.0-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Live Briefing

â†’ **[harshads-git.github.io/feedflow-ai](https://harshads-git.github.io/feedflow-ai)**

Includes topic index, per-topic archives, and a client-side search bar.
*(Updates daily at 07:00 UTC / 12:30 IST)*

---

## What it does

Every day at 07:00 UTC it:

1. **Fetches** from Hacker News (top + new), Reddit (r/MachineLearning, r/LocalLLaMA, r/Python, r/devops), and 8+ RSS feeds (OpenAI, DeepMind, HuggingFace, TechCrunch, Ars Technica, GitHub Blog)
2. **Deduplicates** â€” URL normalisation + Jaccard title similarity to remove near-duplicates
3. **Scores** each story 0â€“10 using GPT-4o-mini against your configured interests â€” cache-first for speed
4. **Summarizes** stories above the threshold: 3-paragraph summary, key takeaways, AI-generated headline
5. **Enriches** each story with live web context via DuckDuckGo before summarising
6. **Builds** a briefing with an AI-generated executive summary and topic clustering
7. **Delivers** via email (inline-styled HTML), Discord webhook, or Slack
8. **Publishes** to GitHub Pages with per-topic archive pages and a client-side search widget

The whole run takes about 45 seconds and costs roughly **$0.02** in API credits.

---

## Why I built this from scratch

I tried existing tools â€” RSS aggregators, news apps, AI newsletter services. None of them let me control:
- *Which* sources get fetched
- *How* relevance is scored (my interests, not an algorithm's)
- *Where* the output goes
- The actual prompt that generates the summary

Building it myself meant I understand every part of it, I can debug it when it breaks, and I can extend it however I want.

---

## Quick start

```bash
# Clone and install (uv recommended)
git clone https://github.com/Harshads-git/feedflow-ai.git
cd feedflow-ai
uv sync

# Interactive setup wizard
feedflow-ai --setup

# Or configure manually
cp .env.example .env
# Edit .env â€” add your AI key and interests

# Validate setup
feedflow-ai --check

# Dry run (no saves, no delivery)
feedflow-ai --dry-run

# Full run
feedflow-ai --run
```

---

## Configuration

Everything lives in `.env`:

```env
# Required â€” at least one AI key
OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=...
# ANTHROPIC_API_KEY=...

# What you actually care about (AI uses this to score relevance)
USER_INTERESTS=AI, machine learning, Python, open source, developer tools

# Only include stories that score above this (0-10)
SCORE_THRESHOLD=6

# Optional: AI model override (default: gpt-4o-mini)
AI_MODEL=gpt-4o-mini

# Optional: email delivery
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-app-password
EMAIL_TO=you@gmail.com

# Optional: Discord webhook
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Sources are configured in `data/sources.json` â€” enable/disable any source and set per-source fetch limits.

---

## CLI Reference

```
feedflow-ai --run              Full pipeline (fetch â†’ score â†’ summarize â†’ deliver)
feedflow-ai --dry-run          Run pipeline but skip saving and delivery
feedflow-ai --setup            Interactive setup wizard
feedflow-ai --status           Last run info + configuration summary
feedflow-ai --briefing         Print most recent briefing to terminal
feedflow-ai --sources-list     All configured sources with health status
feedflow-ai --config           Full configuration + active delivery channels
feedflow-ai --source-stats     Per-source fetch health and error history
feedflow-ai --cache-stats      Score cache hit rate, size, and TTL stats
feedflow-ai --cost-report      AI API cost: daily and weekly spend from ledger
feedflow-ai --retry-stats      Circuit breaker events and throttle history
feedflow-ai --preview-email    Render latest briefing as email HTML, open in browser
feedflow-ai --check            Validate config and API keys (exit 0 = OK)
feedflow-ai --version          Print version

# Advanced
feedflow-ai --run --date 2026-07-10         Re-run for a specific date
feedflow-ai --run --no-enrich               Skip web context fetching (faster)
feedflow-ai --run --log-level DEBUG         Verbose pipeline output
feedflow-ai --dry-run --sources custom.json Test with a different sources file
```

---

## Architecture

```
sources.json
    â†“
[FETCH] â†’ RSS / HN API / Reddit / GitHub (concurrent, async)
    â†“
[DEDUP] â†’ URL normalise + Jaccard title similarity
    â†“
[SCORE] â†’ AI scores each story 0â€“10 (cache-first; circuit breaker + retry budget)
    â†“
[ENRICH] â†’ DuckDuckGo web context per story
    â†“
[SUMMARIZE] â†’ AI: 3-paragraph summary + key points + AI headline + topic labels
    â†“
[BUILD] â†’ Briefing: executive summary + topic clustering + metadata
    â†“
[STORE] â†’ data/briefings/YYYY-MM-DD.json + cost ledger JSONL
    â†“
[RENDER] â†’ docs/YYYY-MM-DD.html + docs/index.html (with search + topic nav)
         â†’ docs/topics.html + docs/topic-{slug}.html + docs/search.json
         â†’ docs/archive.html
    â†“
[DELIVER] â†’ Email (inline-styled HTML) + Discord + Slack + Custom webhooks
```

Each stage is independent. If the Reddit scraper goes down, the rest of the pipeline continues.

### Reliability features (Days 21â€“27)
| Feature | What it does |
|---------|-------------|
| **Score cache** | 24h TTL SQLite-backed cache; skip AI calls for seen stories |
| **Source health** | Per-source error tracking; auto-disables flaky sources |
| **Cost ledger** | JSONL append-log of every AI call; daily/weekly spend reports |
| **Retry budget** | Circuit breaker (CLOSEDâ†’OPENâ†’HALF_OPEN FSM); adaptive concurrency throttling based on rolling error-rate window |
| **Semantic dedup** | Jaccard + embedding similarity to catch paraphrased duplicates |
| **Topic clustering** | AI-assigned topic labels; per-topic archive pages |

---

## GitHub Pages output

Each run produces/updates:

| File | Description |
|------|-------------|
| `docs/index.html` | Latest briefing with sticky search bar + topic pills nav |
| `docs/YYYY-MM-DD.html` | Permanent per-day briefing URL |
| `docs/archive.html` | All briefings, newest first |
| `docs/topics.html` | Topic grid (all topics with story counts) |
| `docs/topic-{slug}.html` | Per-topic story archive |
| `docs/search.json` | Client-side search index (cumulative, 90-day window) |

---

## Project structure

```
src/
â”œâ”€â”€ main.py              # CLI â€” 16 commands, 1462 lines
â”œâ”€â”€ orchestrator.py      # Wires all pipeline stages
â”œâ”€â”€ config.py            # Pydantic Settings from .env
â”œâ”€â”€ models.py            # NewsItem â†’ ScoredItem â†’ SummarizedItem â†’ Briefing
â”œâ”€â”€ __version__.py       # Single-source version (1.0.0)
â”œâ”€â”€ scrapers/            # RSS, HackerNews, Reddit, GitHub + ScraperFactory
â”œâ”€â”€ deduplicator.py      # URL normalise + Jaccard dedup
â”œâ”€â”€ ai/                  # AIProviderFactory, scorer (cache-aware), summarizer
â”œâ”€â”€ briefing.py          # BriefingBuilder + BriefingStore
â”œâ”€â”€ renderers/           # Markdown, HTML, GitHubPagesWriter (topic pages + search)
â”œâ”€â”€ delivery/            # Email (inline template), Discord, Slack, webhook, dispatcher
â””â”€â”€ pipeline/            # RetryBudget (circuit breaker), CostLedger, SourceHealth,
                         # ScoreCache, EventLogger

data/
â”œâ”€â”€ sources.json         # Which sources to fetch (edit this!)
â”œâ”€â”€ briefings/           # Daily briefings as JSON
â”œâ”€â”€ score_cache.json     # AI score cache (24h TTL)
â”œâ”€â”€ cost_log.jsonl       # AI cost ledger (cumulative)
â”œâ”€â”€ retry_budget.jsonl   # Circuit breaker event log
â””â”€â”€ logs/                # JSONL pipeline event log (one file per day)

docs/                    # GitHub Pages output (auto-generated)
tests/                   # 550+ unit tests
.github/workflows/       # ci.yml (lint + test matrix) + daily.yml (cron run)
```

---

## AI providers

Supports OpenAI (default), Google Gemini, and Anthropic Claude. Set `AI_MODEL` in `.env`:

```env
AI_MODEL=gpt-4o-mini              # OpenAI (default, cheapest)
AI_MODEL=gemini-1.5-flash         # Google Gemini
AI_MODEL=claude-3-haiku-20240307  # Anthropic Claude
```

---

## Running costs

With default settings (14 sources, GPT-4o-mini):
- ~300 stories fetched per day
- ~30 pass the score threshold  
- ~$0.01â€“0.03 per day in OpenAI credits

30 days â‰ˆ **$0.30â€“$0.90**. Cheaper than a coffee.

Check your spend anytime: `feedflow-ai --cost-report`

---

## Development

```bash
# Install dev dependencies
uv sync --dev

# Run tests
uv run pytest tests/ -q

# Run with coverage
uv run pytest tests/ --cov=src --cov-report=term-missing

# Lint + format check
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Preview email output
feedflow-ai --preview-email
```

Tests run on Python 3.11 and 3.12 via GitHub Actions on every push.

---

## Roadmap

The 30-day build is complete. Future ideas:

- [ ] **Telegram delivery** â€” more widely used than Discord for me
- [ ] **Weekly digest mode** â€” summarize the week's top 10
- [ ] **Obsidian export** â€” save briefings to my knowledge base as Markdown
- [ ] **MCP server** â€” expose briefings via Model Context Protocol for Claude Desktop

---

## License

MIT â€” do whatever you want with it.

---

*Built in 30 days, 1 hour/day. [See the CHANGELOG](CHANGELOG.md) for the full journey.*

